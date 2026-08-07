from setuptools import find_packages, setup

package_name = "multi_arm_simulation"

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
                "config/domain_randomization.yaml",
                "config/hardware_adapters.yaml",
            ],
        ),
        (
            "share/" + package_name + "/scenarios",
            [
                "scenarios/single_arm.yaml",
                "scenarios/dual_arm.yaml",
                "scenarios/conflict.yaml",
            ],
        ),
        (
            "share/" + package_name + "/launch",
            [
                "launch/simulation_scenario.launch.py",
            ],
        ),
    ],
    install_requires=["setuptools", "pyyaml", "numpy"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="M6.S Simulation Infrastructure",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "scene_generator = multi_arm_simulation.scene_generator:main",
            "dataset_pipeline_node = multi_arm_simulation.dataset_pipeline_node:main",
        ],
    },
)