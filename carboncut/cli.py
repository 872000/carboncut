"""CarbonCut CLI: log, dashboard, challenge, tips.

Examples:
  python -m carboncut log --demo
  python -m carboncut log transport --mode car_gasoline --km 25
  python -m carboncut log energy --source grid --kwh 9.5
  python -m carboncut log diet --meal beef --count 1
  python -m carboncut dashboard --days 30 --out ./dashboard
  python -m carboncut challenge create --name "Cut 10%" --target-pct 10 \\
      --start 2026-10-01 --end 2026-10-07
  python -m carboncut challenge join --id 1 --user sam
  python -m carboncut challenge leaderboard --id 1
  python -m carboncut tips
"""
from __future__ import annotations

import argparse
import os
from datetime import date

from . import db
from . import challenges as challenge_lib
from . import dashboard as dashboard_lib
from . import demo as demo_lib
from . import tips as tips_lib
from .emissions import load_factors, summarize


def _conn(args):
    return db.connect(args.db)


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- log
def cmd_log(args) -> int:
    conn = _conn(args)
    if args.demo:
        info = demo_lib.seed_demo(conn)
        print(f"Seeded demo data for {', '.join(info['users'])} "
              f"+ challenge #{info['challenge_id']} "
              f"({info['challenge']}).")
        print("Try: python -m carboncut dashboard --out ./dashboard")
        return 0
    kinds = {
        "transport": (args.mode, args.km, "km"),
        "energy": (args.source, args.kwh, "kWh"),
        "diet": (args.meal, args.count, "meals"),
    }
    detail, amount, unit = kinds[args.kind]
    if detail is None or amount is None:
        raise SystemExit(f"--{'mode' if args.kind=='transport' else 'source' if args.kind=='energy' else 'meal'} "
                         f"and --{'km' if args.kind=='transport' else 'kwh' if args.kind=='energy' else 'count'} "
                         f"are required for {args.kind}")
    row_id = db.log_activity(
        conn, user=args.user, date=args.date or _today(),
        category=args.kind, detail=detail, amount=amount)
    print(f"Logged #{row_id}: {args.user} {args.kind}/{detail} "
          f"{amount} {unit} on {args.date or _today()}")
    return 0


# ---------------------------------------------------------- dashboard
def cmd_dashboard(args) -> int:
    conn = _conn(args)
    factors = load_factors()
    rows = db.fetch_activities(conn, user=args.user)
    out = dashboard_lib.render_dashboard(rows, factors, args.out,
                                         days=args.days, user=args.user)
    total = out["summary"]["total"]
    print(f"Dashboard for {args.user}: {total:.1f} kgCO2e "
          f"(last {args.days} days, target {out['target']} kg/day)")
    print(f"  category chart: {out['category']}")
    print(f"  trend chart:    {out['trend']}")
    return 0


# ---------------------------------------------------------- challenge
def cmd_challenge(args) -> int:
    conn = _conn(args)
    factors = load_factors()
    if args.action == "create":
        cid = challenge_lib.create(
            conn, factors, name=args.name, target_pct=args.target_pct,
            start=args.start, end=args.end, baseline_days=args.baseline_days)
        print(f"Created challenge #{cid}: {args.name} "
              f"(-{args.target_pct}% from {args.start} to {args.end})")
    elif args.action == "join":
        challenge_lib.join(conn, args.id, args.user)
        print(f"{args.user} joined challenge #{args.id}")
    elif args.action == "list":
        rows = db.list_challenges(conn)
        if not rows:
            print("No challenges yet. Create one with `challenge create`.")
        for r in rows:
            members = ", ".join(db.challenge_members(conn, r["id"])) or "-"
            print(f"#{r['id']} {r['name']} (-{r['target_pct']}%, "
                  f"{r['start_date']}..{r['end_date']}) members: {members}")
    elif args.action == "leaderboard":
        board = challenge_lib.leaderboard(conn, factors, args.id)
        ch = db.get_challenge(conn, args.id)
        print(f"Leaderboard: {ch['name']} (target -{ch['target_pct']}%)")
        print(f"{'rank':<4} {'user':<10} {'baseline':>9} {'current':>8} "
              f"{'cut':>7}  target")
        for r in board:
            mark = "HIT" if r["hit_target"] else ""
            print(f"{r['rank']:<4} {r['user']:<10} "
                  f"{r['baseline_kg_per_day']:>8.1f} "
                  f"{r['current_kg_per_day']:>7.1f} "
                  f"{r['reduction_pct']:>6.1f}%  {mark}")
    return 0


# --------------------------------------------------------------- tips
def cmd_tips(args) -> int:
    conn = _conn(args)
    factors = load_factors()
    rows = db.fetch_activities(conn, user=args.user)
    tips = tips_lib.generate_tips(rows, factors, days=args.days)
    print(tips_lib.format_tips(tips))
    return 0


# ---------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="carboncut",
        description="CarbonCut: track your footprint, race your team to cut it.")
    p.add_argument("--db", default=None,
                   help="SQLite path (default ~/.local/share/carboncut/carboncut.db,"
                        " or $CARBONCUT_DB)")
    sub = p.add_subparsers(dest="command", required=True)

    lg = sub.add_parser("log", help="Log an activity (or seed demo data)")
    lg.add_argument("kind", nargs="?", choices=("transport", "energy", "diet"))
    lg.add_argument("--demo", action="store_true",
                    help="seed bundled demo data instead of logging")
    lg.add_argument("--user", default="me")
    lg.add_argument("--date", default=None, help="YYYY-MM-DD (default today)")
    lg.add_argument("--mode", help="transport mode, e.g. car_gasoline")
    lg.add_argument("--km", type=float, help="kilometres travelled")
    lg.add_argument("--source", help="energy source, e.g. grid")
    lg.add_argument("--kwh", type=float, help="kWh consumed")
    lg.add_argument("--meal", help="meal type, e.g. beef")
    lg.add_argument("--count", type=float, help="number of meals")
    lg.set_defaults(func=cmd_log)

    dbsh = sub.add_parser("dashboard", help="Render footprint charts")
    dbsh.add_argument("--user", default="me")
    dbsh.add_argument("--days", type=int, default=30)
    dbsh.add_argument("--out", default="carboncut_dashboard",
                      help="output directory for PNGs")
    dbsh.set_defaults(func=cmd_dashboard)

    ch = sub.add_parser("challenge", help="Team challenges")
    chsub = ch.add_subparsers(dest="action", required=True)

    chc = chsub.add_parser("create", help="create a challenge")
    chc.add_argument("--name", required=True)
    chc.add_argument("--target-pct", type=float, required=True,
                     help="reduction target, e.g. 10 for -10%")
    chc.add_argument("--start", required=True, help="YYYY-MM-DD")
    chc.add_argument("--end", required=True, help="YYYY-MM-DD")
    chc.add_argument("--baseline-days", type=int, default=7)

    chj = chsub.add_parser("join", help="join a challenge")
    chj.add_argument("--id", type=int, required=True)
    chj.add_argument("--user", required=True)

    chl = chsub.add_parser("list", help="list challenges")

    chb = chsub.add_parser("leaderboard", help="rank members by reduction")
    chb.add_argument("--id", type=int, required=True)
    ch.set_defaults(func=cmd_challenge)

    tp = sub.add_parser("tips", help="personalized reduction suggestions")
    tp.add_argument("--user", default="me")
    tp.add_argument("--days", type=int, default=30)
    tp.set_defaults(func=cmd_tips)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
