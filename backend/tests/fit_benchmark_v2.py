# ruff: noqa: E501
"""Synthetic fit-scoring benchmark (ADR-019). Fictional students, organizations, and postings only.

60 postings; each has a relevance label per profile (3 strong, 2 good, 1 marginal, 0 irrelevant).
The EE/CS profile drove the v2 rules (traps and fixes were written by the same author, so its
numbers are optimistic); the software-only profile is the overfitting check. Location is not part
of the relevance labels.
"""

from dataclasses import dataclass
from datetime import date

from app.enums import RemoteMode, RemotePreference


@dataclass(frozen=True)
class Posting:
    title: str
    organization: str
    description: str
    location: str
    mode: RemoteMode | None
    label: int  # relevance for the EE/CS profile
    tag: str
    age: int


EE_PROFILE: dict[str, object] = dict(
    skills=[
        "Python",
        "C",
        "Go",
        "Verilog",
        "PCB design",
        "Machine Learning",
        "Rust",
        "MATLAB",
        "Embedded Systems",
        "Git",
    ],
    courses=[
        "Digital Logic Design",
        "Signals and Systems",
        "Data Structures and Algorithms",
        "Circuits I",
        "Computer Architecture",
        "Linear Algebra",
        "Machine Learning",
    ],
    interests=["embedded systems", "robotics", "chip design", "machine learning"],
    projects=[
        {
            "name": "FPGA UART Controller",
            "description": "Verilog UART transceiver on an FPGA board, tested in simulation with testbenches",
        },
        {
            "name": "Line Following Robot",
            "description": "Microcontroller C firmware with PID control, motor drivers and sensor boards",
        },
    ],
    research=[
        {
            "name": "Edge Neural Network Inference",
            "description": "Quantized neural networks running on low power microcontrollers",
        }
    ],
    preferred_locations=["San Jose, CA", "Bay Area"],
    remote_preference=RemotePreference.HYBRID_PREFERRED,
    availability_start=date(2027, 5, 15),
    availability_end=date(2027, 8, 31),
)

SW_PROFILE: dict[str, object] = dict(
    skills=["Python", "Java", "Go", "SQL", "React", "Docker", "Git"],
    courses=["Data Structures and Algorithms", "Databases", "Operating Systems", "Linear Algebra"],
    interests=["backend systems", "cloud", "data science"],
    projects=[
        {
            "name": "Campus Marketplace API",
            "description": "Python REST API with SQL storage, Docker deployment and a React front end",
        },
        {
            "name": "Log Pipeline",
            "description": "Go service that streams logs into a database for dashboards",
        },
    ],
    research=[],
    preferred_locations=["San Jose, CA"],
    remote_preference=RemotePreference.NO_PREFERENCE,
    availability_start=date(2027, 5, 15),
    availability_end=date(2027, 8, 31),
)

# Relevance for the software-only profile, by posting title (anything else is 0).
SW_LABELS: dict[str, int] = {
    "Backend Engineering Intern (Go)": 3,
    "Golang Infrastructure Intern": 3,
    "Software Engineer Intern": 3,
    "Cloud DevOps Intern": 3,
    "Python Developer Intern": 3,
    "Data Science Intern": 3,
    "Software Engineering Intern - Systems": 3,
    "Machine Learning Engineer Intern": 2,
    "Data Analyst Intern": 2,
    "Frontend Engineering Intern": 2,
    "Rust Compiler Intern": 2,
    "Robotics Software Intern": 2,
    "Embedded Linux Intern": 2,
    "Embedded Firmware Intern": 1,
    "Embedded Software Engineering Intern": 1,
    "Computer Vision Intern": 1,
    "Deep Learning Intern": 1,
    "IT Support Intern": 1,
    "ML Research Intern - Edge Inference": 1,
    "Test Automation Hardware Intern": 1,
    "Firmware Test Engineering Intern": 1,
    "Technical Writer Intern": 1,
    "Robotics Controls Intern": 1,
    "Research Intern - Signal Processing": 1,
}

L = "San Jose, CA"
R = "Remote - US"
POSTINGS: list[Posting] = []
_MODES = {
    "onsite": RemoteMode.ONSITE,
    "hybrid": RemoteMode.HYBRID,
    "remote": RemoteMode.REMOTE,
    None: None,
}


def add(
    t: str, o: str, d: str, loc: str, mode: str | None, label: int, tag: str, age: int = 10
) -> None:
    POSTINGS.append(Posting(t, o, d, loc, _MODES[mode], label, tag, age))


# strong hardware
add(
    "Digital Design Intern",
    "Northwind Silicon",
    "Join the RTL team to design and simulate digital blocks in Verilog, run synthesis, and validate on FPGA prototypes. Coursework in digital logic and computer architecture expected.",
    L,
    "onsite",
    3,
    "hw",
)
add(
    "ASIC Verification Intern",
    "Aurora Semiconductor",
    "Write SystemVerilog testbenches and UVM environments to verify RTL for a next generation chip. Scripting in Python is a plus.",
    "Sunnyvale, CA",
    "onsite",
    3,
    "hw-syn",
)
add(
    "PCB Design Intern",
    "Brightpath Devices",
    "Support schematic capture and PCB layout for embedded boards. Learn signal integrity, bring-up, and work with firmware engineers.",
    "Santa Clara, California",
    "onsite",
    3,
    "hw",
)
add(
    "Printed Circuit Board Layout Intern",
    "Lumen Instruments",
    "Assist senior engineers with printed circuit board layout, library parts, and design reviews for sensor products.",
    "San Francisco Bay Area",
    "hybrid",
    3,
    "hw-syn",
)
add(
    "Embedded Firmware Intern",
    "Cobalt Robotics",
    "Develop C firmware for microcontrollers, write drivers for sensors and motor controllers, and debug with oscilloscopes and logic analyzers.",
    L,
    "hybrid",
    3,
    "hw",
)
add(
    "Embedded Software Engineering Intern",
    "Delta Wearables",
    "Work on bare-metal and RTOS software for ARM Cortex-M devices in C and C++. Bring-up of new boards and peripherals.",
    "Mountain View, CA",
    "onsite",
    3,
    "hw-syn",
)
add(
    "Hardware Engineering Intern",
    "Orbit Systems",
    "Contribute to analog and digital circuit design, lab validation, and schematic review for a consumer device. Experience with MATLAB and SPICE helpful.",
    "Fremont, CA",
    "onsite",
    3,
    "hw",
)
add(
    "FPGA Engineering Intern",
    "Quasar Networks",
    "Implement packet processing logic on FPGAs using Verilog or VHDL, simulate, and test on hardware.",
    L,
    "onsite",
    3,
    "hw",
)
add(
    "Robotics Controls Intern",
    "Cobalt Robotics",
    "Implement motion control and sensor fusion in C++ and Python for mobile robots. PID control experience is a plus.",
    "Palo Alto, CA",
    "hybrid",
    3,
    "hw",
)
add(
    "Chip Design Intern - Physical Design",
    "Aurora Semiconductor",
    "Support place and route, timing closure, and floorplanning for an ASIC. Scripting in Python and Tcl.",
    "San Jose, CA",
    "onsite",
    3,
    "hw-syn",
)
add(
    "Silicon Validation Intern",
    "Northwind Silicon",
    "Bring up and validate first silicon, write test programs in C and Python, and debug on the lab bench using scopes.",
    "Santa Clara, CA",
    "onsite",
    3,
    "hw",
)
add(
    "Firmware Test Engineering Intern",
    "Brightpath Devices",
    "Build automated tests for device firmware in Python, using hardware in the loop rigs and embedded targets.",
    R,
    "remote",
    2,
    "hw",
)
add(
    "Analog Circuit Design Intern",
    "Lumen Instruments",
    "Design and simulate analog front end circuits, run SPICE, and measure prototypes in the lab. Circuits coursework required.",
    "Milpitas, CA",
    "onsite",
    2,
    "hw",
)
add(
    "Computer Architecture Research Intern",
    "Orbit Systems",
    "Explore microarchitecture ideas using cycle accurate simulators written in C++ and Python. Computer architecture coursework required.",
    "Remote - US",
    None,
    2,
    "hw-nomode",
)
add(
    "Test Automation Hardware Intern",
    "Delta Wearables",
    "Create bench automation scripts in Python to control instruments, collect measurements, and report results for board bring-up.",
    "San Jose, CA",
    "onsite",
    2,
    "hw",
)
# ML / software relevant
add(
    "Machine Learning Engineer Intern",
    "Helix Analytics",
    "Train and evaluate machine learning models in Python and PyTorch, build data pipelines, and deploy to production.",
    R,
    "remote",
    3,
    "ml",
)
add(
    "ML Research Intern - Edge Inference",
    "Quasar Networks",
    "Research efficient neural network inference on microcontrollers. Quantization, C and Python. ML coursework strongly preferred.",
    L,
    "hybrid",
    3,
    "ml",
)
add(
    "Deep Learning Intern",
    "Helix Analytics",
    "Build neural networks for computer vision tasks using Python. Strong linear algebra and deep learning background expected.",
    "Remote - US",
    None,
    2,
    "ml-syn",
)
add(
    "Computer Vision Intern",
    "Cobalt Robotics",
    "Develop perception models for robots in Python and C++, label data, and evaluate on embedded GPUs.",
    "Palo Alto, CA",
    "hybrid",
    3,
    "ml",
)
add(
    "Backend Engineering Intern (Go)",
    "Meridian Cloud",
    "Build backend services in Go with Kubernetes and Postgres. Experience with Go, Python, or Rust is a plus.",
    "San Francisco, CA",
    "hybrid",
    2,
    "sw-go",
)
add(
    "Software Engineering Intern - Systems",
    "Meridian Cloud",
    "Work on low level systems software in C and Rust, including memory management, concurrency, and performance tooling.",
    "Sunnyvale, CA",
    "onsite",
    2,
    "sw",
)
add(
    "Golang Infrastructure Intern",
    "Meridian Cloud",
    "Write infrastructure tooling in Golang, including CLIs and controllers for container platforms.",
    R,
    "remote",
    2,
    "sw-go",
)
add(
    "Software Engineer Intern",
    "Fjord Labs",
    "Develop features across our Python backend and data layer, with data structures and algorithms fundamentals.",
    "San Jose, CA",
    "hybrid",
    2,
    "sw",
)
add(
    "Data Science Intern",
    "Helix Analytics",
    "Analyze datasets with Python and SQL, build dashboards, and apply basic machine learning. Linear algebra helpful.",
    R,
    "remote",
    2,
    "ml",
)
add(
    "Python Developer Intern",
    "Fjord Labs",
    "Build internal tools with python3, write unit tests, and automate workflows for the operations team.",
    "Remote - US",
    None,
    1,
    "sw-syn",
)
# marginal
add(
    "Data Analyst Intern",
    "Fjord Labs",
    "Use SQL and Excel to analyze business metrics and create reports. Python a plus.",
    "San Jose, CA",
    "hybrid",
    1,
    "adj",
)
add(
    "Mechanical Design Intern",
    "Orbit Systems",
    "CAD modeling, tolerance analysis and prototyping for enclosures and mounting hardware. Work with electrical engineers on integration.",
    "Fremont, CA",
    "onsite",
    1,
    "adj",
)
add(
    "Frontend Engineering Intern",
    "Fjord Labs",
    "Build user interfaces with React, HTML and CSS, and collaborate with designers.",
    "San Jose, CA",
    "hybrid",
    1,
    "adj",
)
add(
    "IT Support Intern",
    "Fjord Labs",
    "Help employees with laptops, networking, and software installs. Learn basic scripting in Python.",
    "Austin, TX",
    "onsite",
    1,
    "adj",
)
add(
    "Manufacturing Test Intern",
    "Delta Wearables",
    "Support production test of electronic assemblies, debug failures at the line, and maintain test fixtures.",
    "Austin, TX",
    "onsite",
    1,
    "adj",
)
add(
    "Power Systems Engineering Intern",
    "Voltgrid Energy",
    "Model power electronics and grid equipment using MATLAB, and support lab testing of converters.",
    "Houston, TX",
    "onsite",
    1,
    "adj",
)
add(
    "Research Intern - Signal Processing",
    "Quasar Networks",
    "Develop signal processing algorithms in MATLAB and Python for wireless links. Signals and systems coursework expected.",
    "Remote - US",
    "remote",
    2,
    "adj",
)
add(
    "Quality Engineering Intern",
    "Brightpath Devices",
    "Review device documentation, run test procedures, and file defect reports.",
    L,
    "onsite",
    1,
    "adj",
)
# traps / irrelevant
add(
    "Go-To-Market Strategy Intern",
    "Sable Software",
    "Support our go-to-market team with competitive research, pricing analysis, and launch plans. Go to market experience is a plus.",
    "San Jose, CA",
    "hybrid",
    0,
    "trap-go",
)
add(
    "Marketing Intern",
    "Sable Software",
    "Help plan campaigns and prepare briefing material for our C-suite. Great writing skills required, a go-getter attitude helps.",
    "San Francisco, CA",
    "hybrid",
    0,
    "trap-c",
)
add(
    "Executive Assistant Intern",
    "Sable Software",
    "Support the C-suite and C-level leaders with scheduling, travel, and board materials. Plan to go above and beyond.",
    "San Jose, CA",
    "onsite",
    0,
    "trap-c",
)
add(
    "Web Design Intern",
    "Pixel Harbor",
    "Create landing pages using HTML, CSS and JavaScript. Learn responsive design and accessibility.",
    R,
    "remote",
    0,
    "trap-ml",
)
add(
    "Content Marketing Intern",
    "Pixel Harbor",
    "Write blog posts and email campaigns, and keep HTML templates up to date.",
    "Remote - US",
    None,
    0,
    "trap-ml",
)
add(
    "Facilities Intern",
    "Granite Builders",
    "Support rust-proof coating inspection and field logistics on steel structures. Safety training provided.",
    "Houston, TX",
    "onsite",
    0,
    "trap-rust",
)
add(
    "Construction Management Intern",
    "Granite Builders",
    "Learn project scheduling and site coordination. Ability to go on site daily, rust-resistant gear provided.",
    "Austin, TX",
    "onsite",
    0,
    "trap-rust",
)
add(
    "Finance Intern",
    "Maple Capital",
    "Assist with financial modeling, budgeting, and month end close. Advanced Excel preferred.",
    "New York, NY",
    "onsite",
    0,
    "irr",
)
add(
    "Human Resources Intern",
    "Maple Capital",
    "Support recruiting coordination, onboarding, and HR operations.",
    "Chicago, IL",
    "onsite",
    0,
    "irr",
)
add(
    "Legal Intern",
    "Maple Capital",
    "Draft memos, conduct legal research, and organize contracts for the in-house counsel.",
    "San Francisco, CA",
    "onsite",
    0,
    "irr",
)
add(
    "Graphic Design Intern",
    "Pixel Harbor",
    "Design brand assets and social graphics. Portfolio required. Remote friendly.",
    R,
    "remote",
    0,
    "irr",
)
add(
    "Sales Development Intern",
    "Sable Software",
    "Prospect and qualify leads, run outreach to customers, and keep CRM records current. Go-getters welcome.",
    "San Jose, CA",
    "hybrid",
    0,
    "trap-go",
)
add(
    "Customer Success Intern",
    "Sable Software",
    "Help onboard customers, answer product questions, and learn how to go beyond expectations.",
    R,
    "remote",
    0,
    "irr",
)
add(
    "Biology Research Intern",
    "Cedar Biosciences",
    "Assist wet lab experiments, cell culture, and data entry. Basic statistics helpful.",
    "South San Francisco, CA",
    "onsite",
    0,
    "irr",
)
add(
    "Rust Compiler Intern",
    "Fjord Labs",
    "Contribute to a compiler toolchain written in Rust, working on code generation and diagnostics.",
    R,
    "remote",
    2,
    "sw",
)
add(
    "Cloud DevOps Intern",
    "Meridian Cloud",
    "Automate deployments with Kubernetes and Terraform, write scripts in Python, and improve observability.",
    "Remote - US",
    "remote",
    1,
    "adj",
)
add(
    "Hardware Product Management Intern",
    "Orbit Systems",
    "Help define requirements for consumer electronics and work with engineering teams on schedules. Technical background preferred.",
    L,
    "hybrid",
    1,
    "adj",
)
add(
    "Mechanical Engineering Intern - HVAC",
    "Granite Builders",
    "Support HVAC design calculations and CAD drawings for commercial buildings.",
    "Austin, TX",
    "onsite",
    0,
    "irr",
)
add(
    "Embedded Linux Intern",
    "Delta Wearables",
    "Port and customize Linux for embedded devices, write device drivers in C, and work with bootloaders.",
    "Remote - US",
    None,
    3,
    "hw-nomode",
)
add(
    "RF Hardware Intern",
    "Quasar Networks",
    "Support RF circuit design and test of wireless boards, including schematic review and lab measurements.",
    "San Diego, CA",
    "onsite",
    2,
    "hw",
)
add(
    "Robotics Software Intern",
    "Cobalt Robotics",
    "Build navigation and control software for robots in C++ and Python, using ROS.",
    "San Jose, CA",
    "hybrid",
    3,
    "hw",
)
add(
    "FPGA Prototyping Intern (Remote)",
    "Quasar Networks",
    "Prototype logic designs in Verilog on FPGA boards remotely with lab hardware shipped to you.",
    "Remote - US",
    None,
    3,
    "hw-nomode",
)
add(
    "Operations Intern",
    "Sable Software",
    "Support daily operations, vendor coordination, and process documentation. Go with the flow attitude.",
    "Denver, CO",
    "onsite",
    0,
    "irr",
)
add(
    "Technical Writer Intern",
    "Brightpath Devices",
    "Write documentation for embedded products and developer guides, working with firmware engineers.",
    "Santa Clara, CA",
    "hybrid",
    1,
    "adj",
)
add(
    "Digital Marketing Analyst Intern",
    "Pixel Harbor",
    "Measure campaign performance with analytics tools and machine learning based attribution reports.",
    R,
    "remote",
    0,
    "irr",
)
