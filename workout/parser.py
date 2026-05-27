import xml.etree.ElementTree as ET
import json
import re
from pathlib import Path
from models.data import Workout, WorkoutInterval


_SLOPE_RE = re.compile(r"#([-+]?\d+(?:\.\d+)?)\s*%\s*SLOPE#", re.IGNORECASE)



def _zone_name(pct: float) -> str:
    """Naziv intervala prema % FTP — usklađeno s intervals.icu zonama."""
    if pct <= 0.55: return "Recovery"
    if pct <= 0.75: return "Endurance"
    if pct <= 0.90: return "Tempo"
    if pct <= 1.05: return "Threshold"
    if pct <= 1.20: return "VO2 Max"
    if pct <= 1.50: return "Anaerobic"
    return "Neuromuscular"

class ZWOParser:
    """Parser za Zwift .zwo workout format"""

    def parse(self, path) -> Workout:
        import io
        if isinstance(path, str):
            tree = ET.parse(io.StringIO(path))
        elif isinstance(path, io.StringIO):
            tree = ET.parse(path)
        else:
            tree = ET.parse(path)
        root = tree.getroot()

        name = (root.findtext("name") or root.findtext("n") or
                root.get("name") or root.findtext("workout_file/name") or "Workout")
        description = root.findtext("description", "")
        author = root.findtext("author", "")

        workout = Workout(name=name, description=description, author=author)

        workout_tag = root.find("workout")
        if workout_tag is None:
            raise ValueError("Invalid ZWO file: missing <workout> tag")

        for segment in workout_tag:
            intervals = self._parse_segment(segment)
            workout.intervals.extend(intervals)

        return workout

    def _slope_from_segment(self, segment) -> float | None:
        """Čita #X.X% SLOPE# iz textevent child elemenata ZWO segmenta."""
        for child in segment:
            if child.tag.lower() == "textevent":
                msg = child.get("message", "") or child.get("Message", "")
                m = _SLOPE_RE.search(msg)
                if m:
                    return float(m.group(1))
        # Provjeri i name atribut
        name = segment.get("name", "")
        m = _SLOPE_RE.search(name)
        if m:
            return float(m.group(1))
        return None

    def _name_from_segment(self, segment, default: str) -> str:
        """Čita naziv segmenta, ignorira #SLOPE# tagove."""
        name = segment.get("name") or segment.get("Name") or ""
        # Ukloni slope tag iz naziva
        name_clean = _SLOPE_RE.sub("", name).strip()
        if name_clean:
            return name_clean
        # Provjeri textevent koji nije slope
        for child in segment:
            if child.tag.lower() == "textevent":
                msg = child.get("message", "") or child.get("Message", "")
                if msg and not _SLOPE_RE.search(msg):
                    return msg.strip()
        return default

    def _parse_segment(self, segment) -> list[WorkoutInterval]:
        tag = segment.tag.lower()

        if tag == "steadystate":
            slope = self._slope_from_segment(segment)
            _pct = float(segment.get("Power", 0.5))
            return [WorkoutInterval(
                name=self._name_from_segment(segment, _zone_name(_pct)),
                duration=int(float(segment.get("Duration", 0))),
                power_pct=float(segment.get("Power", 0)),
                power_pct_end=float(segment.get("Power", 0)),
                type="steadystate",
                slope=slope,
            )]

        elif tag == "warmup":
            low   = float(segment.get("PowerLow", 0.4))
            high  = float(segment.get("PowerHigh", 0.75))
            slope = self._slope_from_segment(segment)
            return [WorkoutInterval(
                name=self._name_from_segment(segment, "Warmup"),
                duration=int(float(segment.get("Duration", 0))),
                power_pct=low,
                power_pct_end=high,
                type="warmup",
                slope=slope,
            )]

        elif tag == "cooldown":
            low   = float(segment.get("PowerLow", 0.4))
            high  = float(segment.get("PowerHigh", 0.75))
            slope = self._slope_from_segment(segment)
            return [WorkoutInterval(
                name=self._name_from_segment(segment, "Cooldown"),
                duration=int(float(segment.get("Duration", 0))),
                power_pct=high,
                power_pct_end=low,
                type="cooldown",
                slope=slope,
            )]

        elif tag == "ramp":
            low  = float(segment.get("PowerLow",  0.5))
            high = float(segment.get("PowerHigh", low))
            slope = self._slope_from_segment(segment)
            default_name = "Warmup" if high >= low else "Cooldown"
            return [WorkoutInterval(
                name=self._name_from_segment(segment, default_name),
                duration=int(float(segment.get("Duration", 0))),
                power_pct=low,
                power_pct_end=high,
                type="ramp",
                slope=slope,
            )]

        elif tag == "freeride":
            return [WorkoutInterval(
                name="Free Ride",
                duration=int(float(segment.get("Duration", 0))),
                power_pct=0.0,
                power_pct_end=0.0,
                type="freeride"
            )]

        elif tag == "intervals":
            repeat       = int(segment.get("Repeat", 1))
            on_duration  = int(float(segment.get("OnDuration", 0)))
            off_duration = int(float(segment.get("OffDuration", 0)))
            on_power     = float(segment.get("OnPower", 0))
            off_power    = float(segment.get("OffPower", 0))
            slope        = self._slope_from_segment(segment)
            on_name      = self._name_from_segment(segment, _zone_name(on_power))

            result = []
            for _ in range(repeat):
                result.append(WorkoutInterval(
                    name=on_name,
                    duration=on_duration,
                    power_pct=on_power,
                    power_pct_end=on_power,
                    type="intervals",
                    slope=slope,
                ))
                if off_duration > 0:
                    result.append(WorkoutInterval(
                        name="Recovery",
                        duration=off_duration,
                        power_pct=off_power,
                        power_pct_end=off_power,
                        type="intervals",
                    ))
            return result

        return []


class IntervalsParser:
    """
    Parser za intervals.icu JSON workout format.

    Podržava:
    - flat korake: { duration, power: {value, units}, text }
    - repeat blokove: { repeat, steps: [...] }  (rekurzivno)
    - ramp korake: { duration, ramp: true, power: {start, end, units} }
    - _power field: gotovi watti koje intervals.icu već izračuna
    - slope mod: text "#2.0% SLOPE#" → set_grade umjesto set_target_power
    - units: "w" (direktni watti) ili "%ftp" (množi s ftp)
    """

    def parse(self, path: str | Path) -> Workout:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.parse_dict(data)

    def parse_dict(self, data: dict) -> Workout:
        name = data.get("name") or data.get("workout_name") or "Workout"
        # FTP: uzimamo iz roota, fallback na sportSettings, fallback 240
        ftp = (
            data.get("ftp")
            or data.get("sportSettings", {}).get("ftp")
            or 240
        )

        workout = Workout(name=name, ftp=int(ftp))
        steps = data.get("steps", [])
        workout.intervals = self._flatten_steps(steps, ftp)
        return workout

    def _flatten_steps(self, steps: list, ftp: int) -> list[WorkoutInterval]:
        result = []
        for step in steps:
            # intervals.icu koristi "reps", neki formati koriste "repeat"
            repeat_count = step.get("reps") or step.get("repeat")
            if repeat_count and "steps" in step:
                count = int(repeat_count)
                inner = self._flatten_steps(step.get("steps", []), ftp)
                for _ in range(count):
                    result.extend(inner)
            else:
                iv = self._parse_step(step, ftp)
                if iv:
                    result.append(iv)
        return result

    def _parse_step(self, step: dict, ftp: int) -> WorkoutInterval | None:
        duration = int(step.get("duration", 0))
        if duration <= 0:
            return None

        text = step.get("text", "")
        is_ramp = bool(step.get("ramp", False))

        # --- slope detekcija iz text taga ---
        slope = None
        m = _SLOPE_RE.search(text)
        if m:
            slope = float(m.group(1))

        # --- snaga ---
        power_obj = step.get("power", {})
        _power_obj = step.get("_power", {})  # intervals.icu pre-calculated watts

        units = power_obj.get("units", "w").lower()

        if is_ramp:
            # ramp: power ima start i end
            if _power_obj:
                # koristimo _power koji ima točne apsolutne vrijednosti
                w_start = float(_power_obj.get("start", _power_obj.get("value", 0)))
                w_end   = float(_power_obj.get("end",   _power_obj.get("value", 0)))
                pct_start = w_start / ftp if ftp else 0.0
                pct_end   = w_end   / ftp if ftp else 0.0
            else:
                raw_start = float(power_obj.get("start", 0))
                raw_end   = float(power_obj.get("end",   0))
                if units == "%ftp":
                    pct_start = raw_start / 100.0
                    pct_end   = raw_end   / 100.0
                else:
                    pct_start = raw_start / ftp if ftp else 0.0
                    pct_end   = raw_end   / ftp if ftp else 0.0

            iv_type = "ramp"
            name = text if text and not m else ("Warmup" if pct_end > pct_start else "Cooldown")

        else:
            # steady state
            if _power_obj:
                w = float(_power_obj.get("value", _power_obj.get("start", 0)))
                pct_start = w / ftp if ftp else 0.0
            else:
                raw = float(power_obj.get("value", 0))
                if units == "%ftp":
                    pct_start = raw / 100.0
                else:
                    pct_start = raw / ftp if ftp else 0.0
            pct_end = pct_start
            iv_type = "steadystate"
            name = text if (text and not m) else _zone_name(pct_start)

        return WorkoutInterval(
            name=name or _zone_name(pct_start if "pct_start" in dir() else 0.5),
            duration=duration,
            power_pct=round(pct_start, 4),
            power_pct_end=round(pct_end, 4),
            type=iv_type,
            slope=slope,
            text=text,
        )


class DescriptionParser:
    """
    Parsira intervals.icu plain text workout description format.
    Koristi se kao fallback kad workout_doc.steps nema slope tagove.
    
    Format:
        - 15m Ramp 55-75% FTP WarmUp
        3x
        - 5m 95% FTP Threshold
        - 10m 88% FTP #1.5% SLOPE# SweetSpot
    """

    _DUR_RE   = re.compile(r'(\d+(?:\.\d+)?)\s*(s|m|h)(?:\s|$)', re.IGNORECASE)
    _POWER_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(%(?:\s*ftp)?|w\b)', re.IGNORECASE)
    _RAMP_RE  = re.compile(r'ramp\s+(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*%', re.IGNORECASE)
    _RAMP_W_RE = re.compile(r'ramp\s+(\d+)-(\d+)\s*w\b', re.IGNORECASE)
    _RANGE_RE = re.compile(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*%', re.IGNORECASE)  # npr. 70-74%
    _CADENCE_RE = re.compile(r'@?\s*(\d+)(?:-(\d+))?\s*rpm', re.IGNORECASE)  # @85rpm ili @88-92rpm
    _SLOPE_RE = _SLOPE_RE  # reuse global
    _RPT_RE   = re.compile(r'^(?:main\s+set\s+)?(\d+)x\s*$', re.IGNORECASE)

    def parse(self, description: str, ftp: int = 240, name: str = "Workout") -> Workout:
        workout = Workout(name=name, ftp=ftp)
        workout.description = description
        intervals = self._parse_lines(description.strip().splitlines(), ftp)
        # Post-processing: prvi ramp gore bez naziva → Warmup
        #                  zadnji ramp dolje bez naziva → Cooldown
        _NAMELESS = {"ftp", "ramp", "warmup", "cooldown", ""}
        if intervals:
            first = intervals[0]
            if (first.type == "ramp"
                    and first.power_pct_end >= first.power_pct
                    and first.name.lower() in _NAMELESS):
                first.name = "Warmup"
            last = intervals[-1]
            if (last.type == "ramp"
                    and last.power_pct_end <= last.power_pct
                    and last.name.lower() in _NAMELESS):
                last.name = "Cooldown"
        workout.intervals = intervals
        return workout

    def _parse_lines(self, lines: list, ftp: int) -> list:
        result = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line:
                continue
            rm = self._RPT_RE.match(line)
            if rm:
                count = int(rm.group(1))
                # sakupi blok dok ne naiđemo na prazni red ili novu repeat oznaku ili kraj
                block_lines = []
                while i < len(lines):
                    bl = lines[i].strip()
                    if not bl or self._RPT_RE.match(bl):
                        break
                    block_lines.append(lines[i])
                    i += 1
                inner = self._parse_lines(block_lines, ftp)
                for _ in range(count):
                    result.extend(inner)
                continue
            if line.startswith('-'):
                iv = self._parse_step(line[1:].strip(), ftp)
                if iv:
                    result.append(iv)
        return result

    def _clean_name(self, name: str) -> str:
        """Ukloni artefakte iz naziva intervala: @, FTP, zaostale %, itd."""
        name = re.sub(r'%\s*ftp', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bftp\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'@', '', name)
        name = re.sub(r'\s+', ' ', name)
        return name.strip(' -')

    def _parse_step(self, line: str, ftp: int):
        # Ukloni zagrade s wattima koje intervals.icu dodaje: (132-187w), (209w)
        line = re.sub(r'\(\d+(?:-\d+)?w\)', '', line, flags=re.IGNORECASE).strip()
        # Izvuci preporučenu kadencu ako postoji (@85rpm ili @88-92rpm)
        cadence_rpm = 0
        rpm_m = self._CADENCE_RE.search(line)
        if rpm_m:
            try:
                rpm_lo = int(rpm_m.group(1))
                rpm_hi = int(rpm_m.group(2)) if rpm_m.group(2) else rpm_lo
                cadence_rpm = round((rpm_lo + rpm_hi) / 2)
            except Exception:
                cadence_rpm = 0
        # Ukloni kadenciju iz linije da ne smeta daljnjem parsiranju
        line = self._CADENCE_RE.sub('', line).strip()

        dur_m = self._DUR_RE.search(line)
        if not dur_m:
            return None
        val, unit = float(dur_m.group(1)), dur_m.group(2).lower()
        duration = int(val * (1 if unit == 's' else 60 if unit == 'm' else 3600))

        slope = None
        sm = self._SLOPE_RE.search(line)
        if sm:
            slope = float(sm.group(1))

        ramp_w_m = self._RAMP_W_RE.search(line)
        ramp_m   = self._RAMP_RE.search(line)
        if ramp_w_m:
            # Ramp u wattima → konverzija u % FTP
            p_start = round(float(ramp_w_m.group(1)) / ftp, 4)
            p_end   = round(float(ramp_w_m.group(2)) / ftp, 4)
            name = self._RAMP_W_RE.sub('', line)
            name = self._DUR_RE.sub('', name).strip(' -')
        elif ramp_m:
            p_start = float(ramp_m.group(1)) / 100
            p_end   = float(ramp_m.group(2)) / 100
            name = self._RAMP_RE.sub('', line)
            name = self._DUR_RE.sub('', name).strip(' -')
        if ramp_w_m or ramp_m:
            _GENERIC_RAMP = {"ramp", "warmup", "warm up", "warm-up", "cooldown",
                              "cool down", "cool-down", ""}
            default_name = "Warmup" if p_end >= p_start else "Cooldown"
            if not name or name.lower() in _GENERIC_RAMP:
                name = default_name
            return WorkoutInterval(
                name=name,
                duration=duration,
                power_pct=p_start,
                power_pct_end=p_end,
                type="ramp",
                slope=slope,
                cadence_rpm=cadence_rpm,
            )

        # Raspon bez "Ramp" keyworda: npr. "70-74%" → uzmi sredinu kao steady state
        range_m = self._RANGE_RE.search(line)
        if range_m:
            p_lo = float(range_m.group(1)) / 100
            p_hi = float(range_m.group(2)) / 100
            pct  = round((p_lo + p_hi) / 2, 4)
            name = self._RANGE_RE.sub('', line)
            name = self._DUR_RE.sub('', name)
            name = self._clean_name(name)
            _GENERIC = {"steady", "steadystate", "interval", "work", "on", "off",
                        "recovery", "recover", "rest"}
            if not name or name.lower() in _GENERIC:
                name = _zone_name(pct)
            return WorkoutInterval(
                name=name,
                duration=duration,
                power_pct=pct,
                power_pct_end=pct,
                type="steadystate",
                slope=slope,
                cadence_rpm=cadence_rpm,
            )

        pm = self._POWER_RE.search(line)
        if not pm:
            return None
        pval, punit = float(pm.group(1)), pm.group(2).strip().lower()
        pct = pval / 100 if '%' in punit else pval / ftp

        # naziv = ukloni trajanje, snagu, slope tag
        name = self._SLOPE_RE.sub('', line)
        name = self._DUR_RE.sub('', name)
        name = self._POWER_RE.sub('', name)
        name = self._clean_name(name)

        # Normaliziraj generičke nazive iz intervals.icu exporta
        _GENERIC = {"steady", "steadystate", "interval", "work", "on", "off",
                    "recovery", "recover", "rest"}
        if name.lower() in _GENERIC or not name:
            name = _zone_name(pct)

        return WorkoutInterval(
            name=name or _zone_name(pct_start if "pct_start" in dir() else 0.5),
            duration=duration,
            power_pct=round(pct, 4),
            power_pct_end=round(pct, 4),
            type="steadystate",
            slope=slope,
            cadence_rpm=cadence_rpm,
        )
