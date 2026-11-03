from emporio.capture import PacedBackend


def test_capture_pacing_spaces_requests_without_real_sleep():
    class Clock:
        now = 100.0
        waits = []
        def time(self):
            return self.now
        def sleep(self, seconds):
            self.waits.append(seconds)
            self.now += seconds
    class Backend:
        model = 'fixture'
        calls = 0
        def complete(self, **kwargs):
            self.calls += 1
            return {'content': 'fixture'}
    clock, backend = Clock(), Backend()
    paced = PacedBackend(backend, 25, clock=clock.time, sleeper=clock.sleep)
    paced.complete()
    clock.now += 5
    paced.complete()
    assert clock.waits == [20]
    assert backend.calls == 2
    clock.now += 30
    paced.complete()
    assert clock.waits == [20]


def test_capture_does_not_retry_provider_errors():
    import pytest
    class Backend:
        model = 'fixture'
        calls = 0
        def complete(self, **kwargs):
            self.calls += 1
            raise RuntimeError('fixture rate limit')
    backend = Backend()
    paced = PacedBackend(backend, 0)
    with pytest.raises(RuntimeError):
        paced.complete()
    assert backend.calls == 1
