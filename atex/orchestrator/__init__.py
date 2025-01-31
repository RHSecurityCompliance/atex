import time


class OrchestratorError(Exception):
    pass


class Orchestrator:
    """
    A scheduler for parallel execution on multiple resources (machines/systems).

    TODO: more description
    """

    def serve_once(self):
        """
        Run the orchestration logic, processing any outstanding requests
        (for provisioning, new test execution, etc.) and returning once these
        are taken care of.

        Returns True to indicate that it should be called again by the user
        (more work to be done), False once all testing is concluded.
        """
        raise NotImplementedError(f"'serve_once' not implemented for {self.__class__.__name__}")

    def serve_forever(self):
        """
        Run the orchestration logic, blocking until all testing is concluded.
        """
        while self.serve_once():
            time.sleep(1)

    def start(self):
        """
        Start the Orchestrator instance, opening any files / allocating
        resources as necessary.
        """
        raise NotImplementedError(f"'start' not implemented for {self.__class__.__name__}")

    def stop(self):
        """
        Stop the Orchestrator instance, freeing all allocated resources.
        """
        raise NotImplementedError(f"'stop' not implemented for {self.__class__.__name__}")

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
