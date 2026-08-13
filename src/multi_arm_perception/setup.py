from setuptools import find_packages, setup

package_name = "multi_arm_perception"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (
            "share/" + package_name + "/config",
            ["config/perception_config.yaml"],
        ),
        (
            "share/" + package_name + "/launch",
            ["launch/perception.launch.py"],
        ),
    ],
    install_requires=["setuptools", "pyyaml", "numpy"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="M6.1 Perception package",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "perception_node = multi_arm_perception.perception_node:main",
            "ground_truth_node = multi_arm_perception.ground_truth_node:main",
            "vision_grounding_node = multi_arm_perception.vision_grounding_node:main",
            "color_detector_node = multi_arm_perception.color_detector_node:main",
            "synthetic_camera_node = multi_arm_perception.synthetic_camera_node:main",
        ],
    },
)