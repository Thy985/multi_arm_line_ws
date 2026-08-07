from setuptools import find_packages, setup

package_name = "multi_arm_manipulation"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (
            "share/" + package_name + "/config",
            ["config/gripper_config.yaml"],
        ),
        (
            "share/" + package_name + "/launch",
            ["launch/manipulation.launch.py"],
        ),
    ],
    install_requires=["setuptools", "pyyaml", "numpy"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="M6.2 Manipulation Layer",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "manipulation_node = multi_arm_manipulation.manipulation_node:main",
        ],
    },
)