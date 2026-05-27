"""
Simulacijski test — workout tick-by-tick bez PyQt6 i BLE.
Testira: cadence range, interpolaciju, beepove, evaluaciju intervala.
"""
import sys
sys.path.insert(0, '.')

from models.data import WorkoutInterval, Workout
from workout.player import WorkoutPlayer
from workout.parser import DescriptionParser

# ── Testni workout ─────────────────────────────────────────────────────────────
# Zone (simulirane iz postavki, FTP=240):
# Z1: 0-132W    → 75 rpm
# Z2: 133-180W  → 85 rpm
# Z3: 181-216W  → 88 rpm
# Z4: 217-252W  → 90 rpm
# Z5: 253-288W  → 95 rpm

POWER_ZONES = [
    {"name": "Z1", "min_val": 0,   "max_val": 132, "cadence_rpm": 75},
    {"name": "Z2", "min_val": 133, "max_val": 180, "cadence_rpm": 85},
    {"name": "Z3", "min_val": 181, "max_val": 216, "cadence_rpm": 88},
    {"name": "Z4", "min_val": 217, "max_val": 252, "cadence_rpm": 90},
    {"name": "Z5", "min_val": 253, "max_val": 288, "cadence_rpm": 95},
    {"name": "Z6", "min_val": 289, "max_val": 360, "cadence_rpm": 100},
    {"name": "Z7", "min_val": 361, "max_val": 600, "cadence_rpm": 105},
]
FTP = 240
CAD_TOL = 5

WORKOUT_TEXT = """- 15s Ramp 55-75%
- 20s 75% FTP @95rpm
- 20s 55% FTP
- 15s Ramp 75-50%"""


def cadence_for_interval(iv, ftp=FTP):
    if iv.cadence_rpm > 0:
        return iv.cadence_rpm
    watts = iv.power_pct * ftp
    for z in POWER_ZONES:
        if z["min_val"] <= watts <= z["max_val"]:
            return z["cadence_rpm"]
    return 0


def fmt_range(lo, hi):
    return f"[{lo:.0f}-{hi:.0f} rpm]"


# ── Parse i setup ──────────────────────────────────────────────────────────────
parser = DescriptionParser()
workout = parser.parse(WORKOUT_TEXT, ftp=FTP, name="Sim Test")
player = WorkoutPlayer()
player.workout = workout
player.is_active = True

print("=" * 60)
print("WORKOUT INTERVALI:")
for i, iv in enumerate(workout.intervals):
    cad_src = f"@{iv.cadence_rpm}rpm (direkt)" if iv.cadence_rpm > 0 else f"{cadence_for_interval(iv)}rpm (zona)"
    print(f"  [{i}] {iv.name:20s} {iv.duration}s  {iv.power_pct*100:.0f}-{iv.power_pct_end*100:.0f}%  kadenca: {cad_src}")
print("=" * 60)

# ── Simulacija ─────────────────────────────────────────────────────────────────
# ── Simulacija ─────────────────────────────────────────────────────────────────

# Stanje
cur_range = (0, 0)
prev_idx = -1
last_interval_avg = 150  # simulirana prosječna snaga (W)

def set_cadence_range(rpm, tol=CAD_TOL):
    global cur_range
    cur_range = (rpm - tol, rpm + tol)

def set_cadence_range_direct(lo, hi):
    global cur_range
    cur_range = (lo, hi)

def evaluate_interval(idx):
    iv = workout.intervals[idx]
    target_w = iv.power_pct * FTP
    avg_w = last_interval_avg
    diff_pct = (avg_w - target_w) / target_w * 100 if target_w > 0 else 0
    if abs(diff_pct) <= 5:
        result = "✅ ZELENA"
    elif abs(diff_pct) <= 15:
        result = "🟡 ŽUTA"
    else:
        result = "🔴 CRVENA"
    print(f"  >> EVAL [{idx}] {iv.name}: target={target_w:.0f}W avg={avg_w:.0f}W diff={diff_pct:+.1f}% → {result}")

def interpolate(remaining_before, cur_idx):
    intervals = workout.intervals
    next_idx = cur_idx + 1
    if next_idx >= len(intervals):
        return
    cur_rpm  = cadence_for_interval(intervals[cur_idx])
    next_rpm = cadence_for_interval(intervals[next_idx])
    if cur_rpm <= 0 or next_rpm <= 0 or cur_rpm == next_rpm:
        return
    alpha = (10 - remaining_before) / 10.0
    alpha = max(0.0, min(1.0, alpha))
    interp = cur_rpm + alpha * (next_rpm - cur_rpm)
    set_cadence_range_direct(interp - CAD_TOL, interp + CAD_TOL)
    print(f"    [lerp] rem={remaining_before}s α={alpha:.1f} rpm={interp:.1f} → {fmt_range(*cur_range)}")

def sim_tick(player, elapsed):
    """Simulirani tick — postavlja elapsed direktno bez wall clock."""
    if not player.workout or not player.is_active:
        return
    player.elapsed = elapsed
    player._interval_elapsed = elapsed - player._interval_start
    current = player.current_interval
    if current and player._interval_elapsed >= current.duration:
        player._next_interval_auto()

# Inicijalno — nema ranga
print(f"\n[INIT] Nema cadence ranga (workout nije učitan)\n")

# Učitaj trening — postavi range prvog intervala
first_iv = workout.intervals[0]
first_rpm = cadence_for_interval(first_iv)
if first_rpm > 0:
    set_cadence_range(first_rpm)
    print(f"[LOAD] Učitan workout → cadence range za '{first_iv.name}': {fmt_range(*cur_range)}\n")

# Tick simulacija
total_secs = sum(iv.duration for iv in workout.intervals) + 2

print(f"{'Sec':>5} {'Idx':>4} {'Rem':>5} {'Range':>12}  Event")
print("-" * 60)

for elapsed in range(1, total_secs + 1):
    # Uzmi remaining PRIJE tick-a
    remaining_before = player.interval_remaining
    cur_idx_before = player.current_idx

    sim_tick(player, elapsed)

    cur_idx_after = player.current_idx
    remaining_after = player.interval_remaining

    events = []

    # Promjena intervala
    if prev_idx != cur_idx_after and prev_idx >= 0:
        evaluate_interval(prev_idx)
        if cur_idx_after < len(workout.intervals):
            events.append(f"🔔 NOVI: '{workout.intervals[cur_idx_after].name}'")
            new_rpm = cadence_for_interval(workout.intervals[cur_idx_after])
            if new_rpm > 0:
                set_cadence_range(new_rpm)

    # Beep 10 sec
    if remaining_before == 10 and prev_idx == cur_idx_before:
        events.append("🔉 BEEP")

    # Interpolacija
    if remaining_before <= 10 and remaining_before > 0 and prev_idx == cur_idx_before:
        interpolate(remaining_before, cur_idx_before)

    prev_idx = cur_idx_after

    event_str = "  ".join(events)
    if events or remaining_before <= 10:
        print(f"{elapsed:>5} {cur_idx_after:>4} {remaining_after:>5}  {fmt_range(*cur_range):>12}  {event_str}")

    if not player.is_active:
        evaluate_interval(cur_idx_after)
        print(f"\n[KRAJ] Workout završen na sec {elapsed}")
        break

print("\n" + "=" * 60)
print("Simulacija završena.")
