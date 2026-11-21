# Architecture snapshot — implemented vs planned
Implemented: public file directory -> `env.state.load_public` -> in-memory Environment -> public list/get/document and closed-mode submit. API calls receive bounded codes and budget. No sealed import. `env.cli` is a local JSONL smoke interface.
Not implemented: official adapter, process/OS isolation, producer, manifest integration, truth, scorer, verifier, harness, replay, security analysis or production authentication. HMAC key resides in Python environment object. `contracts/PROVISIONAL_PHASE_05.md` is not a frozen schema.
