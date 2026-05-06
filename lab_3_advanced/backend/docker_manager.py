import os
import docker
import docker.errors
from typing import Optional


class DockerManager:
    MINIO_IMAGE = "minio/minio:RELEASE.2025-04-22T22-12-26Z"
    CONTAINER_PREFIX = "minio_saas_inst_"

    def __init__(self):
        self.client = docker.from_env()
        self.network_name = os.getenv("MINIO_DOCKER_NETWORK", "minio_saas_net")
        self.port_start = int(os.getenv("PORT_RANGE_START", "9100"))
        self.port_end = int(os.getenv("PORT_RANGE_END", "9250"))
        self._ensure_network()

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def _ensure_network(self):
        try:
            self.client.networks.get(self.network_name)
        except docker.errors.NotFound:
            self.client.networks.create(self.network_name, driver="bridge")

    # ------------------------------------------------------------------
    # Port allocation
    # ------------------------------------------------------------------

    def _used_ports_on_host(self) -> set[int]:
        """Collect all host-side ports currently bound by any container."""
        used: set[int] = set()
        for container in self.client.containers.list(all=True):
            for bindings in container.ports.values():
                if bindings:
                    for b in bindings:
                        try:
                            used.add(int(b["HostPort"]))
                        except (KeyError, ValueError):
                            pass
        return used

    def find_free_ports(self, db_used: set[int], count: int = 2) -> list[int]:
        docker_used = self._used_ports_on_host()
        occupied = docker_used | db_used
        free: list[int] = []
        for port in range(self.port_start, self.port_end):
            if port not in occupied:
                free.append(port)
            if len(free) == count:
                return free
        raise RuntimeError(
            f"No free ports available in range {self.port_start}–{self.port_end}"
        )

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def create_container(
        self,
        instance_name: str,
        access_key: str,
        secret_key: str,
        api_port: int,
        console_port: int,
    ) -> str:
        container = self.client.containers.run(
            self.MINIO_IMAGE,
            command="server /data --console-address ':9001'",
            name=f"{self.CONTAINER_PREFIX}{instance_name}",
            environment={
                "MINIO_ROOT_USER": access_key,
                "MINIO_ROOT_PASSWORD": secret_key,
            },
            ports={
                "9000/tcp": ("0.0.0.0", api_port),
                "9001/tcp": ("0.0.0.0", console_port),
            },
            network=self.network_name,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            labels={"managed-by": "minio-saas", "instance": instance_name},
        )
        return container.id

    def stop_container(self, container_id: str) -> None:
        container = self.client.containers.get(container_id)
        container.stop(timeout=10)

    def start_container(self, container_id: str) -> None:
        container = self.client.containers.get(container_id)
        container.start()

    def remove_container(self, container_id: str) -> None:
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass

    def get_status(self, container_id: str) -> str:
        """Return normalised status: running | stopped | error."""
        try:
            c = self.client.containers.get(container_id)
            if c.status == "running":
                return "running"
            if c.status in ("exited", "dead", "created"):
                return "stopped"
            return "stopped"
        except docker.errors.NotFound:
            return "error"

    def get_container_name(self, container_id: str) -> str:
        c = self.client.containers.get(container_id)
        return c.name

    def get_container_ip(self, container_id: str) -> str:
        c = self.client.containers.get(container_id)
        networks = c.attrs.get("NetworkSettings", {}).get("Networks", {})
        net = networks.get(self.network_name) or next(iter(networks.values()), None)
        if not net or not net.get("IPAddress"):
            raise RuntimeError("Container IP not found on target network.")
        return net["IPAddress"]

    def get_logs(self, container_id: str, tail: int = 100) -> str:
        try:
            c = self.client.containers.get(container_id)
            return c.logs(tail=tail).decode("utf-8", errors="replace")
        except docker.errors.NotFound:
            return ""
        except docker.errors.DockerException as exc:
            return f"Failed to fetch logs from Docker daemon: {exc}"
