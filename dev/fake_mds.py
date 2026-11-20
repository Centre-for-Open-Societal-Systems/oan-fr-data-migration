"""A local stand-in for the Master Data Service, for trying the migration's
Master Data path without one. Serves the three endpoints the registry's
Master Data client reads (core helpers/master_data.py) from the country pack.
Standard library only. No authentication.

  python fake_mds.py --pack /pack/packs [--drop CROP_TEFF,ET04041110] [--port 8000]

--drop leaves out code values or locations (P-codes), to see what the
migration does with a value Master Data does not have.
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from farmer_profile.masterdata import MasterData  # noqa: E402


def build(pack, drop):
    master = MasterData.from_pack(pack)
    values = [{"attribute_id": a, "value_code": c} for a, codes in sorted(master.codes.items())
              for c in sorted(codes) if c not in drop]
    levels, geo = {}, {}
    for node in master.nodes.values():
        if node["level_value_id"] in drop:
            continue
        level_id = f"level-{node['level_mnemonic']}"
        levels[level_id] = node["level_mnemonic"]
        geo.setdefault(level_id, []).append({"level_id": level_id, "level_value_id": node["level_value_id"],
                                             "level_value_mnemonic": node["level_value_mnemonic"],
                                             "parent_level_value_id": node["parent"]})
    return values, levels, geo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="/pack/packs")
    parser.add_argument("--drop", default="")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    values, levels, geo = build(args.pack, {d.strip() for d in args.drop.split(",") if d.strip()})

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            request = body.get("request_body") or {}
            payload = request.get("request_payload") or {}
            if self.path == "/attributes/get_attribute_values":
                page = request.get("pagination_request") or {"current_page": 1, "page_size": len(values)}
                size, number = int(page["page_size"]), int(page["current_page"])
                out = {"attribute_values": values[(number - 1) * size:number * size], "total": len(values)}
            elif self.path == "/geo/get_all_geo_levels":
                out = [{"level_id": k, "level_mnemonic": v} for k, v in levels.items()]
            elif self.path == "/geo/get_geo_level_values":
                out = geo.get(payload.get("level_id"), [])
            else:
                self.send_error(404)
                return
            data = json.dumps({"response_header": {"response_status": "SUCCESS"},
                               "response_body": {"response_payload": out}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    print(f"fake Master Data on :{args.port}: {len(values)} code values, {sum(map(len, geo.values()))} locations",
          flush=True)
    ThreadingHTTPServer(("", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
