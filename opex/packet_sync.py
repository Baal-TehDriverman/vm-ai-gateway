import os, json, hashlib, time, argparse, glob

class OPEXSync:
    """OPEX Checkpoint-and-Acknowledge durable packet bridge.

    Guarantees at-least-once delivery across edge (Android/Termux) and core
    (Garuda Linux) even when the laptop is asleep: payloads are written to a
    checksummed disk queue and only GONE after the core ACKs them.
    """

    def __init__(self, queue_dir="~/opex_queue"):
        self.queue_dir = os.path.expanduser(queue_dir)
        os.makedirs(self.queue_dir, exist_ok=True)

    def _checksum(self, data):
        return hashlib.sha256(f"{int(time.time())}{data}".encode()).hexdigest()

    def enqueue_payload(self, data):
        """Write a payload to the durable queue. Returns the payload_id."""
        payload_id = self._checksum(data)
        file_path = os.path.join(self.queue_dir, f"{payload_id}.json")
        record = {
            "id": payload_id,
            "ts": int(time.time()),
            "data": data,
            "status": "pending",
            "attempts": 0,
        }
        with open(file_path, "w") as f:
            json.dump(record, f)
        return payload_id

    def list_pending(self):
        pending = []
        for fn in os.listdir(self.queue_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.queue_dir, fn)) as f:
                    rec = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if rec.get("status") == "pending":
                pending.append(rec)
        return pending

    def sync_to_core(self, core_ip, core_port=8001):
        """Push all pending payloads to the core endpoint; on HTTP 2xx ACK,
        mark them delivered (checkpoint-and-acknowledge)."""
        import urllib.request, urllib.error

        pending = self.list_pending()
        delivered = 0
        for rec in pending:
            req = urllib.request.Request(
                f"http://{core_ip}:{core_port}/opex/ingest",
                data=json.dumps({"id": rec["id"], "data": rec["data"]}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if 200 <= resp.status < 300:
                        rec["status"] = "delivered"
                        rec["delivered_ts"] = int(time.time())
                        with open(os.path.join(self.queue_dir, f"{rec['id']}.json"), "w") as f:
                            json.dump(rec, f)
                        delivered += 1
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                # core asleep/offline: hold payload, bump attempts — at-least-once
                rec["attempts"] = rec.get("attempts", 0) + 1
                with open(os.path.join(self.queue_dir, f"{rec['id']}.json"), "w") as f:
                    json.dump(rec, f)
        return {"delivered": delivered, "still_pending": len(self.list_pending())}

    @staticmethod
    def verify_record(path):
        """Ad-hoc integrity check: replay the SHA and confirm the payload is intact."""
        with open(path) as f:
            rec = json.load(f)
        expected = hashlib.sha256(f"{rec['ts']}{rec['data']}".encode()).hexdigest()
        return rec["id"] == expected


def main():
    ap = argparse.ArgumentParser(prog="opex", description="OPEX bidirectional packet bridge")
    ap.add_argument("--enqueue", metavar="DATA", help="queue a payload and print its id")
    ap.add_argument("--status", action="store_true", help="show pending queue")
    ap.add_argument("--sync", metavar="CORE_IP", help="deliver pending to core")
    ap.add_argument("--verify", metavar="ID", help="verify integrity of a queued payload")
    ap.add_argument("--queue-dir", default="~/opex_queue", help="override queue path")
    args = ap.parse_args()

    sync = OPEXSync(args.queue_dir)

    if args.enqueue:
        pid = sync.enqueue_payload(args.enqueue)
        print(f"ENQUEUED {pid}")
    elif args.status:
        for rec in sync.list_pending():
            print(f"PENDING {rec['id']} attempts={rec['attempts']}")
    elif args.sync:
        result = sync.sync_to_core(args.sync)
        print(f"SYNC delivered={result['delivered']} still_pending={result['still_pending']}")
    elif args.verify:
        path = os.path.join(sync.queue_dir, f"{args.verify}.json")
        ok = os.path.exists(path) and OPEXSync.verify_record(path)
        print("VERIFY", "OK (integrity intact)" if ok else "MISSING_OR_CORRUPT")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()