from setuptools import find_packages, setup

package_name = "multi_arm_robot_description"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (
            "share/" + package_name + "/config",
            [
                "config/robot.yaml",
                "config/capability.yaml",
                "config/base_interface.yaml",
            ],
        ),
        (
            "share/" + package_name + "/launch",
            [
                "launch/capability_registry.launch.py",
            ],
        ),
    ],
    install_requires=["setuptools", "pyyaml", "jinja2"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="M6.0 Robot Description Layer",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "capability_registry_node = multi_arm_robot_description.capability_registry_node:main",
            "generate_robot_description = multi_arm_robot_description.robot_description_generator:main",
        ],
    },
)