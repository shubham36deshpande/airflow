#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Utilities for creating a virtual environment."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import jinja2
from jinja2 import select_autoescape

from airflow.utils.process_utils import execute_in_subprocess


def _generate_venv_cmd(tmp_dir: str, python_bin: str, system_site_packages: bool) -> list[str]:
    """We are using venv command instead of venv module to allow creation of venv for different python versions."""
    if python_bin is None:
        python_bin = sys.executable
    cmd = [python_bin, "-m", "venv", tmp_dir]
    if system_site_packages:
        cmd.append("--system-site-packages")
    return cmd


def _generate_install_cmd_from_list(
    venv_directory: str, requirements: List[str], install_options: List[str], installer: str) -> List[str]:
    """
    Generate the command to install packages using the specified installer.

    :param venv_directory: Path to the virtual environment directory.
    :param requirements: List of packages to install.
    :param install_options: Additional options for the installer.
    :param installer: The package installer to use ('pip' or 'uv').
    :return: List of command components to execute.
    """
    if installer == "uv":
        return [f"{venv_directory}/bin/uv", "pip", "install", *install_options, *requirements]
    else:
        return [f"{venv_directory}/bin/pip", "install", *install_options, *requirements]


def _generate_install_cmd_from_file(
    venv_directory: str, requirements_file_path: str, install_options: List[str], installer: str) -> List[str]:
    """
    Generate the command to install packages from a requirements file using the specified installer.

    :param venv_directory: Path to the virtual environment directory.
    :param requirements_file_path: Path to the requirements.txt file.
    :param install_options: Additional options for the installer.
    :param installer: The package installer to use ('pip' or 'uv').
    :return: List of command components to execute.
    """
    if installer == "uv":
        return [f"{venv_directory}/bin/uv", "pip", "install", *install_options, "-r", requirements_file_path]
    else:
        return [f"{venv_directory}/bin/pip", "install", *install_options, "-r", requirements_file_path]


def _generate_pip_conf(conf_file: Path, index_urls: list[str]) -> None:
    if index_urls:
        pip_conf_options = f"index-url = {index_urls[0]}"
        if len(index_urls) > 1:
            pip_conf_options += f"\nextra-index-url = {' '.join(x for x in index_urls[1:])}"
    else:
        pip_conf_options = "no-index = true"
    conf_file.write_text(f"[global]\n{pip_conf_options}")


def prepare_virtualenv(
    venv_directory: str,
    python_bin: str,
    system_site_packages: bool,
    requirements: list[str] | None = None,
    requirements_file_path: str | None = None,
    pip_install_options: list[str] | None = None,
    index_urls: list[str] | None = None,
    installer: str = "pip",
) -> str:
    """
    Create a virtual environment and install the additional python packages.

    :param venv_directory: The path for directory where the environment will be created.
    :param python_bin: Path to the Python executable.
    :param system_site_packages: Whether to include system_site_packages in your virtualenv.
        See virtualenv documentation for more information.
    :param requirements: List of additional python packages.
    :param requirements_file_path: Path to the ``requirements.txt`` file.
    :param pip_install_options: a list of pip install options when installing requirements
        See 'pip install -h' for available options
    :param index_urls: an optional list of index urls to load Python packages from.
        If not provided the system pip conf will be used to source packages from.
    :param installer: The package installer to use 'pip' or 'uv'. Default -> 'pip'.
    :return: Path to a binary file with Python in a virtual environment.
    
    """
    if pip_install_options is None:
        pip_install_options = []

    if index_urls is not None:
        _generate_pip_conf(Path(venv_directory) / "pip.conf", index_urls)

    venv_cmd = _generate_venv_cmd(venv_directory, python_bin, system_site_packages)
    execute_in_subprocess(venv_cmd)

    if requirements is not None and requirements_file_path is not None:
        raise ValueError("Either requirements OR requirements_file_path has to be passed, but not both")

    pip_cmd = None
    if requirements is not None and len(requirements) != 0:
        pip_cmd = _generate_pip_install_cmd_from_list(venv_directory, requirements, pip_install_options)
    if requirements_file_path is not None and requirements_file_path:
        pip_cmd = _generate_pip_install_cmd_from_file(
            venv_directory, requirements_file_path, pip_install_options
        )

    if pip_cmd:
        execute_in_subprocess(pip_cmd)

    return f"{venv_directory}/bin/python"


def write_python_script(
    jinja_context: dict,
    filename: str,
    render_template_as_native_obj: bool = False,
):
    """
    Render the python script to a file to execute in the virtual environment.

    :param jinja_context: The jinja context variables to unpack and replace with its placeholders in the
        template file.
    :param filename: The name of the file to dump the rendered script to.
    :param render_template_as_native_obj: If ``True``, rendered Jinja template would be converted
        to a native Python object
    """
    template_loader = jinja2.FileSystemLoader(searchpath=os.path.dirname(__file__))
    template_env: jinja2.Environment
    if render_template_as_native_obj:
        template_env = jinja2.nativetypes.NativeEnvironment(
            loader=template_loader, undefined=jinja2.StrictUndefined
        )
    else:
        template_env = jinja2.Environment(
            loader=template_loader,
            undefined=jinja2.StrictUndefined,
            autoescape=select_autoescape(["html", "xml"]),
        )
    template = template_env.get_template("python_virtualenv_script.jinja2")
    template.stream(**jinja_context).dump(filename)
