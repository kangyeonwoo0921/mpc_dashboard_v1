"""Screen recommendation rules (recommendation/engine.py): night windows, hybrid shading, hold, modes, safety."""

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from recommendation import engine, settings_store

KST = ZoneInfo("Asia/Seoul")


def live(shade2=100.0, shade1=100.0, t_out=12.0, rh=70.0, connected=True):
    return {"source": "field_collector", "connected": connected, "timestamp": None,
            "environment": {"outdoor_temperature_c": t_out, "solar_w_m2": 500.0, "indoor_rh_pct": rh},
            "actuators": {"shade_screen_2_pct": shade2, "shade_screen_1_pct": shade1}}


def forecast(issue, values, recent=None, status="ok"):
    horizons = [{"h_steps": k + 1, "horizon_min": 5 * (k + 1), "target_time": (issue + timedelta(minutes=5 * (k + 1))).isoformat(),
                 "method": "xgb_expanding", "ghi_w_m2": v, "kc": None, "ghi_clear_w_m2": 800.0} for k, v in enumerate(values)]
    recent = recent if recent is not None else [500.0] * 12
    obs = [{"time": (issue - timedelta(minutes=5 * (len(recent) - 1 - i))).isoformat(), "ghi_w_m2": v, "status": "observed"}
           for i, v in enumerate(recent)]
    return {"status": status, "reason": None, "horizons": horizons if status == "ok" else None, "recent_observations": obs}


def run(now, live_dto, fc, settings=None, state=None, safety=None):
    s = {**settings_store.DEFAULTS, **(settings or {})}
    inp = engine.Inputs(now=now, live=live_dto, safety=safety or {"rain": None, "strong_wind": None},
                        forecast=fc, settings=s, state=state or {})
    return engine.recommend(inp)


NOON = datetime(2026, 10, 12, 12, 2, tzinfo=KST)        # issue bin 12:00
ISSUE = NOON.replace(minute=0)
NIGHT = datetime(2026, 10, 12, 22, 3, tzinfo=KST)


class SunTests(unittest.TestCase):
    def test_sun_events_plausible_for_gimje_october(self):
        sunrise, sunset = engine.sun_events(NOON.date())
        self.assertTrue(6 <= sunrise.hour <= 7 and 17 <= sunset.hour <= 18)

    def test_night_window(self):
        inside, start, end = engine.in_window(NIGHT, -1.0, 0.5)
        self.assertTrue(inside)
        self.assertEqual((start + timedelta(hours=1)).date(), NIGHT.date())
        self.assertFalse(engine.in_window(NOON, -1.0, 0.5)[0])


class ShadeTests(unittest.TestCase):
    def test_no_shading_below_threshold(self):
        payload, _ = run(NOON, live(), forecast(ISSUE, [600.0] * 12))
        shade = payload["screens"]["shade_screen"]
        self.assertEqual((shade["recommended_open_percent"], shade["action"], shade["state"]), (100.0, "hold", "DAY_VENTILATION"))

    def test_forecast_persistence_triggers_shading(self):
        payload, state = run(NOON, live(), forecast(ISSUE, [720.0, 730.0, 710.0] + [650.0] * 9))
        shade = payload["screens"]["shade_screen"]
        self.assertEqual((shade["recommended_open_percent"], shade["action"]), (0.0, "deploy"))
        self.assertEqual(state["shade_held_until"], (ISSUE + timedelta(minutes=15)).isoformat())

    def test_short_spike_does_not_trigger(self):
        payload, _ = run(NOON, live(), forecast(ISSUE, [720.0, 650.0, 720.0] + [600.0] * 9))
        self.assertEqual(payload["screens"]["shade_screen"]["recommended_open_percent"], 100.0)

    def test_measured_mean_triggers_when_forecast_is_lower(self):
        payload, _ = run(NOON, live(), forecast(ISSUE, [650.0] * 12, recent=[500.0] * 9 + [705.0, 710.0, 700.0]))
        self.assertEqual(payload["screens"]["shade_screen"]["recommended_open_percent"], 0.0)

    def test_retract_needs_all_sources_low_and_hold_respected(self):
        state = {"shade_target": 0.0, "shade_held_until": (ISSUE + timedelta(minutes=10)).isoformat()}
        low = forecast(ISSUE, [500.0] * 12, recent=[500.0] * 12)
        payload, _ = run(NOON, live(shade2=0.0), low, state=state)
        self.assertEqual(payload["screens"]["shade_screen"]["recommended_open_percent"], 0.0)        # still held
        state["shade_held_until"] = (ISSUE - timedelta(minutes=5)).isoformat()
        payload, _ = run(NOON, live(shade2=0.0), low, state=state)
        self.assertEqual(payload["screens"]["shade_screen"]["action"], "retract")
        high_measured = forecast(ISSUE, [500.0] * 12, recent=[500.0] * 9 + [720.0] * 3)
        payload, _ = run(NOON, live(shade2=0.0), high_measured, state=state)
        self.assertEqual(payload["screens"]["shade_screen"]["recommended_open_percent"], 0.0)        # measured still high

    def test_modes(self):
        fc = forecast(ISSUE, [750.0] * 12)
        cold, _ = run(NOON, live(), fc, settings={"operation_mode": "cold"})
        self.assertEqual(cold["screens"]["shade_screen"]["state"], "DAY_LIGHT_PRESERVATION")
        night_auto, _ = run(NIGHT, live(), fc)
        self.assertEqual(night_auto["screens"]["shade_screen"]["recommended_open_percent"], 20.0)
        night_hot, _ = run(NIGHT, live(), fc, settings={"operation_mode": "hot"})
        self.assertEqual(night_hot["screens"]["shade_screen"]["recommended_open_percent"], 100.0)

    def test_safety_holds_current(self):
        payload, _ = run(NOON, live(shade2=40.0), forecast(ISSUE, [800.0] * 12), safety={"rain": True, "strong_wind": False})
        shade = payload["screens"]["shade_screen"]
        self.assertEqual((shade["recommended_open_percent"], shade["state"]), (40.0, "SAFETY_OVERRIDE"))
        self.assertTrue(any("천창" in a for a in payload["advisories"]))

    def test_stale_measured_is_ignored(self):
        fc = forecast(ISSUE, [500.0] * 12, recent=[720.0] * 12)
        fc["reason"] = "data_stale"; fc["status"] = "unavailable"; fc["horizons"] = None
        payload, _ = run(NOON, live(), fc)
        self.assertEqual(payload["screens"]["shade_screen"]["recommended_open_percent"], 100.0)
        self.assertEqual(payload["status"], "degraded")

    def test_no_information_holds_actual_position(self):
        payload, _ = run(NOON, live(shade2=57.0), None, state={"shade_target": 100.0})
        shade = payload["screens"]["shade_screen"]
        self.assertEqual((shade["recommended_open_percent"], shade["action"], shade["state"]), (57.0, "hold", "DAY_HOLD"))

    def test_plan_has_13_points(self):
        payload, _ = run(NOON, live(), forecast(ISSUE, [600.0] * 3 + [720.0] * 9))
        plan = payload["screens"]["shade_screen"]["plan_open_percent"]
        self.assertEqual(len(plan), 13)
        self.assertEqual(plan[0], 100.0)
        self.assertIn(0.0, plan[1:])                                         # deployment planned later


class DiffuseTests(unittest.TestCase):
    def test_cold_night_deploys_warm_night_does_not(self):
        cold, _ = run(NIGHT, live(t_out=10.0), None)
        self.assertEqual(cold["screens"]["diffuse_screen"]["recommended_open_percent"], 0.0)
        warm, _ = run(NIGHT, live(t_out=18.0), None)
        self.assertEqual(warm["screens"]["diffuse_screen"]["recommended_open_percent"], 100.0)
        unknown, _ = run(NIGHT, live(t_out=None), None)
        self.assertEqual(unknown["screens"]["diffuse_screen"]["action"], "unavailable")

    def test_day_retracted_and_rh_advisory(self):
        payload, _ = run(NOON, live(rh=99.9), forecast(ISSUE, [600.0] * 12))
        self.assertEqual(payload["screens"]["diffuse_screen"]["recommended_open_percent"], 100.0)
        self.assertTrue(any("습도" in a for a in payload["advisories"]))
        self.assertEqual(payload["settings"]["days_after_transplant"], 20)


if __name__ == "__main__":
    unittest.main()
