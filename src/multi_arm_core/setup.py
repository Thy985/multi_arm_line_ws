from setuptools import find_packages, setup

package_name = "multi_arm_core"

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
                "config/robots.yaml",
            ],
        ),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="Multi-arm coordination core package",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "coordinator_node = multi_arm_core.coordinator_node:main",
        ],
    },
)