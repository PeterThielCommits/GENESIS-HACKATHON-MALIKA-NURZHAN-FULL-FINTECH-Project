.PHONY: test smoke

test:
	python3 -m unittest discover -s tests -t . -p 'test_*.py' -v

smoke:
	printf '%s\n' '{"tool":"list_records","args":{"table":"invoices"}}' '{"tool":"submit","args":{"findings":[]}}' | python3 -m env.cli tests/fixtures/example/public
