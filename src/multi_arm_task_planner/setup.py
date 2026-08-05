from setuptools import find_packages, setup

package_name = "multi_arm_task_planner"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    package_data={
        "multi_arm_task_planner": ["bt_xml/*.xml"],
    },
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="lenovo",
    maintainer_email="lenovo@todo.todo",
    description="Multi-arm task planner package (L6 BehaviorTree)",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "task_planner_node = multi_arm_task_planner.task_planner_node:main",
        ],
    },
)