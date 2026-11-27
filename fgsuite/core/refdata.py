"""Reference data transcribed from EGPC-PSM-GL-017 and ISA-TR84.00.07-2018.

Every table carries its clause reference so that the report can cite it verbatim.
"""

EGPC = "EGPC-PSM-GL-017"
ISA = "ISA-TR84.00.07-2018"

# ---------------------------------------------------------------------------
# Annex C Step 1 (EGPC) / Figure A.2 (ISA): base frequency (likelihood) factor
# ---------------------------------------------------------------------------
EQUIPMENT_BASE_FREQUENCY = {
    "Shell & tube heat exchanger": 2.0,
    "Plate & frame heat exchanger": 3.0,
    "Air-cooled heat exchanger": 2.0,
    "Column/tower/contactor": 2.5,
    "Compressor/expander": 3.0,
    "Pressure vessel/reactor": 2.0,
    "Centrifugal pump": 3.0,
    "Reciprocating pump": 3.0,
    "Atmospheric storage tank": 1.0,
    "LP storage tank": 1.0,
    "Fired heater": 2.0,
    "Pig launcher/receiver": 2.0,
    "Sump/sump pump": 1.0,
    "Piping manifold": 1.0,
    "Single welded pipe segment": 1.0,
    "Production wellheads": 2.0,
}
EQUIPMENT_AR = {
    "Shell & tube heat exchanger": "مبادل حراري (Shell & Tube)",
    "Plate & frame heat exchanger": "مبادل حراري لوحي (Plate & Frame)",
    "Air-cooled heat exchanger": "مبرد هوائي (Air Cooler)",
    "Column/tower/contactor": "برج / عمود / Contactor",
    "Compressor/expander": "ضاغط / Expander",
    "Pressure vessel/reactor": "وعاء ضغط / مفاعل",
    "Centrifugal pump": "طلمبة طاردة مركزية",
    "Reciprocating pump": "طلمبة ترددية",
    "Atmospheric storage tank": "خزان جوي",
    "LP storage tank": "خزان ضغط منخفض",
    "Fired heater": "فرن / سخان ناري",
    "Pig launcher/receiver": "Pig Launcher / Receiver",
    "Sump/sump pump": "Sump / طلمبة Sump",
    "Piping manifold": "مانيفولد مواسير",
    "Single welded pipe segment": "قطعة ماسورة ملحومة",
    "Production wellheads": "رؤوس آبار إنتاج",
}

# Step 2: occupancy adjustment
OCCUPANCY = {
    "rare": (-2.0, "Rare occupancy (<15 min/day) ~1% / rapid escape 1-3 min"),
    "moderate": (-1.0, "Moderate occupancy (routine rounds) ~10% / egress 3-10 min"),
    "high": (0.0, "High occupancy (>30%) / muster + TR, 10-30 min protection"),
}
OCCUPANCY_AR = {
    "rare": "نادر (< 15 دقيقة/يوم ≈ 1%) — هروب سريع 1-3 دقائق",
    "moderate": "متوسط (جولات تشغيل روتينية ≈ 10%) — إخلاء 3-10 دقائق",
    "high": "عالي (تواجد شبه مستمر > 30%) — تجمع + ملجأ مؤقت 10-30 دقيقة",
}

# Step 3: ignition adjustment (fire & flammable gas only)
IGNITION = {
    "low": (-1.5, "Low ignition probability (3%)"),
    "average": (-1.0, "Average ignition probability (10%)"),
    "moderate": (-0.5, "Moderate ignition probability (30%)"),
    "high": (0.0, "High ignition probability (near 100%)"),
}
IGNITION_AR = {
    "low": "منخفض (3%) — لا مصادر اشتعال قوية، تصنيف كهربي سليم",
    "average": "متوسط (10%)",
    "moderate": "معتدل (30%) — مصادر اشتعال متقطعة قريبة",
    "high": "عالي (~100%) — أسطح ساخنة / لهب مكشوف / فرن",
}

# Step 4: base consequence by phase
PHASE_CONSEQUENCE = {"stable_liquid": 1.0, "volatile_liquid": 2.0, "gas": 3.0}
PHASE_AR = {
    "stable_liquid": "سائل مستقر (T < نقطة الوميض)",
    "volatile_liquid": "سائل متطاير (نقطة الوميض < T < نقطة الغليان)",
    "gas": "غاز (T > نقطة الغليان، ويشمل السوائل المبردة)",
}

# Step 4: pressure adjustment (psig upper bounds)
PRESSURE_BANDS = [  # (upper bound psig exclusive, adjustment, label)
    (50.0, -0.5, "Atm to 50 psig"),
    (150.0, 0.0, "50 to 150 psig"),
    (300.0, 0.5, "150 to 300 psig"),
    (1000.0, 1.0, "300 to 1,000 psig"),
    (float("inf"), 1.5, "> 1,000 psig"),
]

# Step 5: flammability environment (flammable gas only)
CONGESTION = {
    "low": (-1.0, "No confinement / low congestion (3D Low)"),
    "medium": (0.0, "Some confinement / moderate congestion (2D Med)"),
    "high": (2.0, "Confinement / high congestion (2D High)"),
}
CONGESTION_AR = {
    "low": "بدون حصر / ازدحام منخفض (3D Low)",
    "medium": "حصر جزئي / ازدحام متوسط (2D Med)",
    "high": "حصر / ازدحام عالي (2D High)",
}

# Step 6: H2S concentration adjustment (v/v ppm upper bounds)
H2S_BANDS = [  # (upper bound ppm exclusive, adjustment or None, label)
    (100.0, None, "< 100 ppm - no H2S analysis required"),
    (1000.0, -1.0, "100 ppm to 1000 ppm"),
    (10000.0, 0.0, "1000 ppm to 1%"),
    (30000.0, 1.0, "1% to 3%"),
    (100000.0, 2.0, "3% to 10%"),
    (float("inf"), 3.0, "> 10%"),
]

# Step 8: grade thresholds (lower bound inclusive, grade, target coverage)
FIRE_GRADES = [(7.0, "A*", 0.90), (5.0, "A", 0.90), (2.0, "B", 0.80), (0.5, "C", 0.60)]
FLAM_GRADES = [(7.0, "A*", 0.90), (5.0, "A", 0.90), (2.0, "B", 0.80), (0.5, "C", 0.60)]
TOXIC_GRADES = [(7.5, "A*", 0.90), (5.5, "A", 0.90), (3.5, "B", 0.80), (1.5, "C", 0.60)]

GRADE_DEFINITION = {
    "A*": "High hydrocarbon processing with high sensitivity",
    "A": "High hazard potential",
    "B": "Moderate hazard potential",
    "C": "Low or very low hazard potential",
    "N/A": "Risk is tolerable without benefit of FGS",
}
GRADE_AR = {
    "A*": "خطورة عالية جداً — يُطلب > 90% ودراسة QRA إضافية (EGPC يقبل ≥ 80% عملياً)",
    "A": "خطورة عالية — 90% (EGPC §8.5 يقبل ≥ 80%)",
    "B": "خطورة متوسطة — 80%",
    "C": "خطورة منخفضة — 60%",
    "N/A": "الخطر مقبول بدون نظام F&G — لا يوجد هدف تغطية",
}
# EGPC §8.5 note / Annex C: A* and A acceptable at >= 80 % (practical relaxation)
EGPC_MIN_ACCEPTABLE_A = 0.80

# ---------------------------------------------------------------------------
# Design basis hazards (ISA Table 5 & Table 6)
# ---------------------------------------------------------------------------
# Fire: radiant heat output (kW) by grade (ISA Table 5 typical applications)
FIRE_RHO_BY_GRADE = {"A*": 10.0, "A": 50.0, "B": 100.0, "C": 250.0}
FIRE_RHO_JUSTIFICATION = {
    "A*": "ISA Table 5: 10 kW RHO - high hazard areas (alarm); detect the smallest incipient fire.",
    "A": "ISA Table 5: 50 kW RHO - high hazard areas (safety action); ~1 ft x 1 ft n-heptane pan fire.",
    "B": "ISA Table 5: 100 kW RHO - medium hazard areas.",
    "C": "ISA Table 5: 250+ kW RHO - low hazard areas.",
}
# Baseline vendor sensitivity: 1 ft^2 n-heptane pan fire ~ 50 kW (EGPC §8.3.1, ISA D.1)
BASELINE_FIRE_KW = 50.0

# Flammable gas: spherical cloud diameter (m) by congestion (ISA Table 6, HSE OTO 93 002)
GAS_CLOUD_BY_CONGESTION = {"high": 5.0, "medium": 7.5, "low": 10.0}
GAS_CLOUD_JUSTIFICATION = {
    "high": "ISA Table 6: 5 m spherical cloud within areas of high confinement & congestion "
            "(minimum cloud able to accelerate flame front to damaging overpressure - HSE OTO 93 002).",
    "medium": "ISA Table 6: 7-8 m spherical cloud within areas of moderate confinement & congestion.",
    "low": "ISA Table 6: 10 m spherical cloud within areas of low confinement & congestion.",
}
# Toxic: ISA 4.5 "5 m H2S cloud size, 8 m H2S cloud size"
TOXIC_CLOUD_DEFAULT = 5.0

# ---------------------------------------------------------------------------
# Set points (EGPC §8.3 / Table A2, API RP 14C)
# ---------------------------------------------------------------------------
POINT_GAS_SETPOINTS = {"alarm_pct_lel": 25.0, "action_pct_lel": 60.0}
OPGD_SETPOINTS = {"alarm_lelm": 1.25, "action_lelm": 3.0}
MIN_SETPOINT_BY_GAS = {  # EGPC §8.3.2 - do not go below (false alarms)
    "Methane": 5.0, "Propane": 10.0, "Gasoline vapour": 20.0,
}
UGLD_ALARM_DB = 6.0  # dB above background (Table A2)

# Gas properties used for detector technology/elevation guidance
GASES = {
    # name: (LEL %v/v, relative density to air, IR-detectable?, notes)
    "Methane": (5.0, 0.55, True, "Lighter than air - mount detectors above leak sources / under roofs."),
    "Natural gas": (4.4, 0.65, True, "Lighter than air."),
    "Ethane": (3.0, 1.04, True, "Near-neutral buoyancy."),
    "Propane": (2.1, 1.55, True, "Heavier than air - mount low (0.3-0.5 m above grade) and in pits."),
    "Butane": (1.8, 2.0, True, "Heavier than air - mount low."),
    "Gasoline vapour": (1.4, 3.0, True, "Heavier than air - mount low."),
    "Hydrogen": (4.0, 0.07, False, "IR detectors cannot detect hydrogen (EGPC A.3) - use catalytic/electrochemical."),
    "Benzene": (1.2, 2.7, False, "Not detected by standard IR LOS (EGPC A.1) - use point detectors tuned for aromatics/PID."),
}

TOXIC_GASES = {
    # name: (IDLH ppm, STEL ppm, TWA ppm, relative density)
    "H2S": (100.0, 15.0, 10.0, 1.19),
    "SO2": (100.0, 5.0, 2.0, 2.26),
    "NH3": (300.0, 35.0, 25.0, 0.59),
    "Cl2": (10.0, 1.0, 0.5, 2.49),
    "CO": (1200.0, 200.0, 25.0, 0.97),
}

# ---------------------------------------------------------------------------
# Detector library (generic - edit with project vendor data sheets)
# ---------------------------------------------------------------------------
# range_m is on-axis range for the BASELINE_FIRE_KW (1 ft^2 n-heptane) fire.
FLAME_DETECTOR_LIBRARY = {
    "Multi-spectrum IR (IR3)": {"range_m": 65.0, "hfov": 90.0, "vfov": 90.0, "edge_factor": 0.50},
    "UV/IR": {"range_m": 15.0, "hfov": 90.0, "vfov": 90.0, "edge_factor": 0.50},
    "UV": {"range_m": 15.0, "hfov": 120.0, "vfov": 120.0, "edge_factor": 0.50},
    "Single IR": {"range_m": 30.0, "hfov": 90.0, "vfov": 90.0, "edge_factor": 0.50},
    "Visual/CCTV flame": {"range_m": 40.0, "hfov": 65.0, "vfov": 50.0, "edge_factor": 0.60},
}
GAS_DETECTOR_LIBRARY = {
    "Point IR (catalytic-free)": {"kind": "point_gas"},
    "Catalytic bead (pellistor)": {"kind": "point_gas"},
    "Open path IR (OPGD)": {"kind": "opgd", "max_path_m": 120.0},
    "Open path laser": {"kind": "opgd", "max_path_m": 200.0},
    "Electrochemical H2S": {"kind": "toxic"},
    "MOS H2S": {"kind": "toxic"},
}

DETECTOR_KINDS = {
    "flame": "Flame detector",
    "point_gas": "Point flammable gas detector",
    "opgd": "Open path gas detector",
    "toxic": "Point toxic gas detector",
}
DETECTOR_KIND_AR = {
    "flame": "كاشف لهب",
    "point_gas": "كاشف غاز قابل للاشتعال (نقطي)",
    "opgd": "كاشف غاز مسار مفتوح (OPGD)",
    "toxic": "كاشف غاز سام (نقطي)",
}
# Annex F symbols
DETECTOR_SYMBOL = {"flame": "USH", "point_gas": "ASH", "opgd": "ASH", "toxic": "OSH"}

# ---------------------------------------------------------------------------
# EGPC §9.1 required inputs and §9.2 deliverables
# ---------------------------------------------------------------------------
REQUIRED_INPUTS = [
    ("target_coverage", "Target coverage", "أهداف التغطية"),
    ("hac", "Hazardous area layout drawings", "رسومات تصنيف المناطق الخطرة"),
    ("plot", "Equipment layout drawings / plot plans", "رسومات توزيع المعدات / Plot Plan"),
    ("pfd", "Process flow diagrams", "مخططات سريان العمليات PFD"),
    ("desc", "Process description", "وصف العملية"),
    ("hmb", "Heat & material balance / stream compositions", "الاتزان الحراري والمادي / تركيب التيارات"),
    ("msds", "MSDS for all chemicals (flash points)", "صحائف بيانات المواد MSDS (نقطة الوميض)"),
    ("studies", "Relevant safety studies (FERA, dispersion, consequence)", "دراسات السلامة (FERA، تشتت، عواقب)"),
    ("prev", "Previous performance targets (if available)", "أهداف أداء سابقة (إن وجدت)"),
    ("phil", "Fire and gas philosophy", "فلسفة الحريق والغاز"),
    ("model3d", "3D model (.nwd / DWG)", "نموذج ثلاثي الأبعاد (nwd / DWG)"),
    ("env", "Environmental conditions (wind rose, temperature)", "الظروف البيئية (وردة الرياح، الحرارة)"),
]

REFERENCES = [
    "EGPC-PSM-GL-017 Rev.0, Fire and Gas Mapping Guideline, Egyptian General Petroleum Corporation, Dec-2022.",
    "ISA-TR84.00.07-2018, Guidance on the Evaluation of Fire, Combustible Gas, and Toxic Gas System Effectiveness.",
    "BS 60080:2020, Hazard detection mapping - Guidance on the placement of permanently installed flame and gas detection devices.",
    "UK HSE RR1123 (2017), Fixed flammable gas detector systems on offshore installations.",
    "UK HSE OTO 93 002, Offshore Gas Detector Siting Criterion - Investigation of Detector Spacing.",
    "API RP 14C (2018) and API RP 14G (2019).",
    "ISO 13702:2015, Control and mitigation of fires and explosions on offshore production installations.",
    "ISA-TR84.00.02, SIS - SIL Evaluation Techniques (PFDavg simplified equations).",
    "FM 3260, Approval Standard for Radiant Energy-Sensing Fire Detectors.",
]
