import argparse
import json
import subprocess
import time

import keyring
import loguru
import requests
from passwork.password_crud import get_password, search_password
from passwork.passwork_api import PassworkAPI
from pathlib2 import Path

from typing import Callable


class Connection:
    address: str
    port: str
    login: str
    password: str

    def __init__(self, address: str, port: str, login: str, password: str):
        self.address = address
        self.port = port
        self.login = login
        self.password = password

    connect: Callable[[self], None | str]


class RDPConnection(Connection):
    def __init__(self, address: str, port: str, login: str, password: str):
        super().__init__(address, port, login, password)

    def connect(self) -> None | str:
        subprocess.run(
            [
                "cmdkey",
                f"/generic:{self.address}",
                f"/user:{self.login}",
                f"/pass:{self.password}",
            ]
        )
        subprocess.run(["mstsc", f"/v:{self.address}:{self.port}"])
        subprocess.run(["cmdkey", f"/delete:{self.address}"])


class SSHConnection(Connection):
    def __init__(self, address: str, port: str, login: str, password: str):
        super().__init__(address, port, login, password)

    def connect(self):
        subprocess.run(
            [
                "plink",
                self.address,
                "-l",
                self.login,
                "-P",
                self.port,
                "-pw",
                self.password,
            ]
        )


def get_session(file: Path) -> PassworkAPI:
    with open(file, "r") as f:
        config = json.load(f)
    if "master" not in config or config["master"] == "":
        return PassworkAPI(config["host"], config["key"])
    return PassworkAPI(config["host"], config["key"], config["master"])


def main(session: PassworkAPI, file: Path) -> None:
    with open(file, "r") as f:
        connection = json.load(f)
    try:
        credentials = search_password(
            session,
            {
                "query": connection["id"],
                "tags": [],
                "colors": [],
                "vaultId": None,
                "includeShared": True,
                "includeShortcuts": False,
            },
        )[0]
        password = get_password(session, credentials["id"])["passwordPlainText"]
    except requests.exceptions.ConnectionError:
        print("Can not connect to server")
        return
    if (protocol := connection["protocol"]) == "rdp":
        RDPConnection(
            connection["address"], connection["port"], credentials["login"], password
        ).connect()
    elif protocol == "ssh":
        SSHConnection(
            connection["address"], connection["port"], credentials["login"], password
        ).connect()


class _Namespace:
    connection: Path
    config: Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("connection", type=Path)
    parser.add_argument("-c", "--config", type=Path, default=Path.cwd() / "config.json")
    args = parser.parse_args(namespace=_Namespace)

    loguru.logger.disable("passwork")
    if not args.config.exists():
        print(f'Config file "{args.config}" does not exist, exiting.')
    if not args.config.is_file():
        print(f'"{args.config}" is not a file, exiting.')

    session = get_session(args.config)
    main(session, args.connection)
