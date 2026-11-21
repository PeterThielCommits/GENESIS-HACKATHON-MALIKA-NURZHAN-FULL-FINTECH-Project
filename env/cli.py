"""Provisional JSON-lines smoke interface; not an official organizer adapter."""
import argparse
import json
import sys
from .server import Environment

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('public_dir')
    parser.add_argument('--max-steps', type=int, default=100)
    args = parser.parse_args()
    # A fixed local demo key makes smoke output reproducible, not secure.
    env = Environment()
    try:
        observation = env.reset(args.public_dir, {'mode': 'CLOSED_EVAL', 'max_steps': args.max_steps, 'cursor_key': b'provisional-smoke-key-not-secret!'})
        print(json.dumps({'observation': observation}, ensure_ascii=False), flush=True)
        for line in sys.stdin:
            try:
                action = json.loads(line)
            except (ValueError, RecursionError):
                action = None
            print(json.dumps(env.step(action), ensure_ascii=False), flush=True)
    except (OSError, ValueError):
        print('invalid public episode or configuration', file=sys.stderr)
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
