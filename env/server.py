"""Provisional closed-evaluation state machine. No scoring or finalize."""
import copy
from .budget import MAX_STEPS, MAX_REQUEST_BYTES
from .cursors import Cursors
from .errors import PublicError
from .state import canonical, load_public
from .tools import execute
from .validation import findings_valid

class Environment:
    def __init__(self):
        self.ready = False

    def reset(self, episode_public_ref, env_config):
        self.ready = False
        if not isinstance(env_config, dict) or set(env_config) != {'max_steps', 'mode', 'cursor_key'}:
            raise ValueError('invalid environment config')
        max_steps, mode, key = env_config['max_steps'], env_config['mode'], env_config['cursor_key']
        if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS or mode != 'CLOSED_EVAL' or not isinstance(key, bytes) or len(key) < 32:
            raise ValueError('invalid environment config')
        data, digest = load_public(episode_public_ref)
        self.data, self.max_steps, self.used = data, max_steps, 0
        self.cursors = Cursors(key, digest)
        self.submitted = False
        self.terminated = self.truncated = False
        self._submission = None
        self.ready = True
        return copy.deepcopy({'company': data['company'], 'policy': data['policy'], 'opening_balances': data['opening_balances'], 'period_calendar': data['period_calendar'], 'max_steps': max_steps, 'steps_remaining': max_steps, 'mode': mode})

    def step(self, action):
        if not self.ready:
            raise RuntimeError('reset required')
        if self.terminated or self.truncated:
            code = 'ALREADY_SUBMITTED' if self.submitted and isinstance(action, dict) and action.get('tool') == 'submit' else 'TERMINATED'
            return self._result({'error': {'code': code}})
        # A malformed action or invalid submit costs an inspection step, so a
        # caller cannot use the submit name to obtain free validation probes.
        is_submit = isinstance(action, dict) and action.get('tool') == 'submit'
        try:
            if len(canonical(action)) > MAX_REQUEST_BYTES:
                raise PublicError('LIMIT')
            if not isinstance(action, dict) or not {'tool', 'args'} <= action.keys() or not action.keys() <= {'tool', 'args', 'action_id'}:
                raise PublicError('BAD_ARGS')
            if 'action_id' in action and (not isinstance(action['action_id'], str) or len(action['action_id']) > 128):
                raise PublicError('BAD_ARGS')
            if not isinstance(action['tool'], str) or not isinstance(action['args'], dict):
                raise PublicError('BAD_ARGS')
            if is_submit:
                if set(action['args']) != {'findings'}:
                    raise PublicError('BAD_ARGS')
                findings_valid(action['args']['findings'])
                self._submission = copy.deepcopy(action['args']['findings'])
                self.submitted = self.terminated = True
                return self._result({'submitted': True})
            result = execute(self, action['tool'], action['args'])
        except PublicError as e:
            result = {'error': {'code': e.code}}
        except (TypeError, ValueError, OverflowError, RecursionError):
            result = {'error': {'code': 'BAD_ARGS'}}
        except Exception:
            result = {'error': {'code': 'INTERNAL'}}
        self.used += 1
        if self.used >= self.max_steps:
            self.truncated = True
        return self._result(result)

    def _result(self, result):
        return copy.deepcopy({'observation': {'result': result, 'steps_remaining': self.max_steps - self.used},
                              'reward': 0, 'terminated': self.terminated,
                              'truncated': self.truncated, 'info': {}})
