from setuptools import setup

package_name = "multi_arm_skill_runtime"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config/skills", [
            "config/skills/pick_object.yaml",
            "config/skills/place_object.yaml",
            "config/skills/move_object.yaml",
        ]),
        ("share/" + package_name + "/launch", [
            "launch/skill_runtime.launch.py",
        ]),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="MultiArm Team",
    maintainer_email="dev@example.com",
    description="Skill Runtime: Manifest + Lifecycle + Registry + Execution",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "skill_node = multi_arm_skill_runtime.skill_node:main",
        ],
    },
)