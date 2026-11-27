"""Design-basis hazards, mapping-method and technology selection with justifications.

Every recommendation returns a ``Decision`` carrying an English justification (for the
report), an Arabic explanation (for the user interface) and the governing clause.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import refdata as R
from .model import Project, Zone
from .ranking import rank_zone


@dataclass
class Decision:
    topic: str
    choice: str
    why_en: str
    why_ar: str
    ref: str
    zone: str = ""


@dataclass
class ZoneBasis:
    fire_rho_kw: float
    gas_cloud_m: float
    toxic_cloud_m: float
    fire_range_factor: float  # multiplier on vendor baseline range


def fire_range_factor(rho_kw: float) -> float:
    """Inverse-square law: received radiant flux ~ RHO / d^2, so for a detector with a fixed
    threshold, detection distance scales with sqrt(RHO / RHO_baseline) (EGPC §8.3.1)."""
    return (max(rho_kw, 1e-6) / R.BASELINE_FIRE_KW) ** 0.5


def zone_basis(project: Project, zone: Zone) -> ZoneBasis:
    zr = rank_zone(project, zone)
    rho = zone.fire_rho_kw
    if rho is None:
        rho = R.FIRE_RHO_BY_GRADE.get(zr["fire"].grade, 100.0)
    cloud = zone.gas_cloud_m or R.GAS_CLOUD_BY_CONGESTION[zone.congestion]
    tox = zone.toxic_cloud_m or R.TOXIC_CLOUD_DEFAULT
    return ZoneBasis(rho, cloud, tox, fire_range_factor(rho))


def recommend_method(project: Project) -> Decision:
    info = project.info
    if info.phase == "feed" and not info.inputs_available.get("model3d"):
        choice = "volumetric"
        en = ("FEED stage without a mature 3D model: prescriptive placement is allowed only for the "
              "initial design (EGPC §8.2.1); the volumetric (geographic) method is selected to quantify "
              "coverage early, then re-verified at 60 % / 90 % 3D model (ISA §5.1-5.2).")
        ar = ("مرحلة FEED بدون نموذج ثلاثي الأبعاد مكتمل: الطريقة الإرشادية (Prescriptive) مسموحة فقط للتصميم "
              "المبدئي (EGPC §8.2.1)، لذلك نختار الطريقة الحجمية (Geographic) لقياس التغطية مبكراً ثم نعيد "
              "التحقق عند اكتمال النموذج 60% و90% (ISA §5.1-5.2).")
    elif info.phase == "existing":
        choice = "volumetric"
        en = ("Existing facility: EGPC §7.2 / §8.2.1 recommend selecting the highly hazardous locations "
              "(Annex C ranking) and verifying them with the geographic or scenario-based method; optimisation "
              "order is re-aim -> small moves -> add detectors.")
        ar = ("منشأة قائمة: يوصي EGPC §7.2 و§8.2.1 باختيار المواقع الأعلى خطورة (تصنيف Annex C) والتحقق منها "
              "بالطريقة الحجمية أو المبنية على السيناريو؛ وترتيب التحسين: تعديل زاوية الكاشف ← تحريك بسيط ← إضافة كواشف.")
    elif info.inputs_available.get("studies") and project.philosophy.gas_philosophy == "release" and any(
            z.indoor for z in project.zones):
        choice = "scenario"
        en = ("Dispersion/QRA studies exist, the gas philosophy is release-based and enclosed modules with "
              "predictable (HVAC) airflow are present: scenario-based mapping is justified (EGPC §8.2.3; "
              "ISA Annex E recommends CFD only for such specialised, predictable environments).")
        ar = ("توجد دراسات تشتت/QRA، والفلسفة مبنية على اكتشاف التسريب، ويوجد مناطق مغلقة بتهوية متوقعة (HVAC): "
              "لذلك الطريقة المبنية على السيناريو مبررة (EGPC §8.2.3)، وISA Annex E يوصي باستخدام CFD فقط في هذه البيئات.")
    else:
        choice = "volumetric"
        en = ("Open/semi-confined process areas: gas migrates to all areas of the congested zone, so the "
              "volumetric method that targets the dangerous cloud size is preferred (ISA Annex E; EGPC §8.2.2 "
              "advantages: consistent, auditable, insensitive to minor changes / MOC).")
        ar = ("مناطق تشغيل مفتوحة/شبه محصورة: الغاز قد يصل لأي مكان في المنطقة المزدحمة، لذلك الطريقة الحجمية "
              "التي تستهدف حجم السحابة الخطِر هي المفضلة (ISA Annex E؛ مزايا EGPC §8.2.2: متسقة، سهلة المراجعة، "
              "ولا تتأثر بالتعديلات البسيطة).")
    return Decision("Gas mapping method", choice, en, ar, "EGPC §8.2 / ISA Annex B & E")


def zone_decisions(project: Project, zone: Zone) -> list[Decision]:
    zr = rank_zone(project, zone)
    b = zone_basis(project, zone)
    out: list[Decision] = []
    zn = zone.name
    fg = zr["fire"].grade
    if fg != "N/A":
        src = "user override" if zone.fire_rho_kw is not None else R.FIRE_RHO_JUSTIFICATION.get(fg, "")
        out.append(Decision(
            "Design-basis fire", f"{b.fire_rho_kw:g} kW RHO",
            f"Fire grade {fg}: {src} Detector ranges are scaled from the vendor 1 ft² n-heptane baseline "
            f"({R.BASELINE_FIRE_KW:g} kW) by sqrt(RHO/50) = x{b.fire_range_factor:.2f} (inverse-square law, EGPC §8.3.1).",
            f"درجة الحريق {fg}: حجم الحريق التصميمي {b.fire_rho_kw:g} kW (ISA Table 5). مدى الكاشف يُحسب من مدى "
            f"المصنّع لحريق n-Heptane مساحة 1 قدم² (≈{R.BASELINE_FIRE_KW:g} kW) مضروباً في √(RHO/50) = {b.fire_range_factor:.2f} "
            "طبقاً لقانون التربيع العكسي للإشعاع (EGPC §8.3.1).",
            "ISA Table 5; EGPC §8.3.1", zn))
    gg = zr["gas"].grade
    if gg != "N/A":
        src = "user override" if zone.gas_cloud_m else R.GAS_CLOUD_JUSTIFICATION[zone.congestion]
        out.append(Decision(
            "Design-basis flammable gas cloud", f"{b.gas_cloud_m:g} m spherical cloud",
            f"Gas grade {gg}; {src}",
            f"درجة الغاز {gg}: سحابة كروية قطرها {b.gas_cloud_m:g} م طبقاً لدرجة الحصر/الازدحام "
            f"({R.CONGESTION_AR[zone.congestion]}) — ISA Table 6 و HSE OTO 93 002: هذه أصغر سحابة قادرة على "
            "تسريع جبهة اللهب لإحداث ضغط انفجار ضار.",
            "ISA Table 6; EGPC §8.2.2.1", zn))
    tg = zr["toxic"].grade
    if tg != "N/A":
        out.append(Decision(
            "Design-basis toxic cloud", f"{b.toxic_cloud_m:g} m H2S cloud",
            f"Toxic grade {tg}; geographic toxic cloud per ISA §4.5 (5 m / 8 m H2S cloud), focusing on walkways, "
            "escape routes and entrances (EGPC §8.2.2.2).",
            f"درجة السمية {tg}: سحابة H2S قطرها {b.toxic_cloud_m:g} م (ISA §4.5)، مع التركيز على الممرات وطرق الهروب "
            "والمداخل (EGPC §8.2.2.2).",
            "ISA §4.5; EGPC §8.2.2.2", zn))
    # Technology
    fluids = {e.fluid for e in project.zone_equipment(zone.id)}
    for f in sorted(fluids):
        g = R.GASES.get(f)
        if not g:
            continue
        lel, rd, ir_ok, note = g
        if ir_ok:
            tech = "Point IR + Open-path IR" if zone.congestion != "high" else "Point IR (congested area)"
            en = (f"{f}: IR detectable, fails safe in 100 % v/v (EGPC A.3). "
                  + ("Open-path IR gives wider coverage along walkways/perimeter. " if zone.congestion != "high"
                     else "Congested area limits open-path beams (ISA B.5.2-17) - point detectors preferred. ")
                  + note)
            ar = (f"{f}: يُكتشف بالأشعة تحت الحمراء ويعمل في تركيز 100% (EGPC A.3). "
                  + ("كاشف المسار المفتوح يعطي تغطية أوسع على الممرات والمحيط. " if zone.congestion != "high"
                     else "المنطقة مزدحمة وتعيق مسار الشعاع (ISA B.5.2) لذلك نفضل الكواشف النقطية. ")
                  + ("أثقل من الهواء: تُركّب الكواشف منخفضة." if rd > 1.1 else
                     "أخف من الهواء: تُركّب الكواشف أعلى مصادر التسريب." if rd < 0.9 else "كثافة قريبة من الهواء."))
        else:
            tech = "Catalytic / gas-specific point detector"
            en = f"{f}: {note}"
            ar = (f"{f}: لا يُكتشف بكواشف IR القياسية (EGPC A.1/A.3) — استخدم كاشف كاتاليتيك أو كاشف مخصص لهذا الغاز.")
        out.append(Decision(f"Gas detector technology ({f})", tech, en, ar, "EGPC Annex A; ISA B.5.2", zn))
    if fg != "N/A":
        tech = "Multi-spectrum IR (IR3)" if not zone.indoor else "UV/IR or IR3"
        out.append(Decision(
            "Flame detector technology", tech,
            "Hydrocarbon fires: IR3 gives the longest range and best false-alarm immunity outdoors (sunlight, "
            "hot work, flare). Indoors UV/IR is acceptable. Heat/smoke detectors are mapped prescriptively "
            "(EGPC Annex A.2).",
            "حرائق هيدروكربونية: كاشف IR3 يعطي أطول مدى وأفضل مناعة ضد الإنذارات الكاذبة في الخارج (الشمس، "
            "اللحام، الشعلة). داخل المباني يمكن استخدام UV/IR. كواشف الحرارة والدخان تُصمم بالطريقة الإرشادية (EGPC A.2).",
            "EGPC Annex A.2; ISA B.5.1-14", zn))
    return out


def philosophy_decisions(project: Project) -> list[Decision]:
    p = project.philosophy
    info = project.info
    out = []
    if p.fire_philosophy == "incipient":
        out.append(Decision("Fire detection philosophy", "Detect incipient fire",
                            "Detect fire as early as practical to limit escalation and allow personnel protective "
                            "actions - suited to manned onshore plants / high value assets (ISA Table 1, EGPC Table B1).",
                            "اكتشاف الحريق في مراحله الأولى للحد من التصعيد وإتاحة الإخلاء — مناسب للمحطات المأهولة "
                            "والأصول عالية القيمة (ISA Table 1 / EGPC Table B1).", "EGPC Annex B Table B1"))
    else:
        out.append(Decision("Fire detection philosophy", "Detect fully developed fire",
                            "Normally unmanned installation with limited fire-fighting: detect fire with potential "
                            "for major damage, isolate fuel (ISA Table 1).",
                            "منشأة غير مأهولة بإمكانيات إطفاء محدودة: اكتشاف الحريق المتطور وعزل الوقود (ISA Table 1).",
                            "EGPC Annex B Table B1"))
    if p.gas_philosophy == "accumulation":
        out.append(Decision("Flammable gas philosophy", "Detect hazardous accumulations",
                            "Gas dispersion is unpredictable in congested areas; detectors are placed to detect the "
                            "threshold cloud that could produce damaging overpressure (ISA Table 2, EGPC Table B2).",
                            "تشتت الغاز غير متوقع في المناطق المزدحمة؛ توضع الكواشف لاكتشاف حجم السحابة الحرج الذي قد "
                            "يسبب ضغط انفجار ضار (EGPC Table B2).", "EGPC Annex B Table B2"))
    else:
        out.append(Decision("Flammable gas philosophy", "Detect credible releases near sources",
                            "Detectors near identified leak sources give early indication before migration to "
                            "ignition sources, supplemented by perimeter detection (ISA Table 2).",
                            "الكواشف قرب مصادر التسريب تعطي إنذاراً مبكراً قبل انتقال الغاز لمصادر الاشتعال، مع كواشف "
                            "محيطية إضافية (EGPC Table B2).", "EGPC Annex B Table B2"))
    out.append(Decision("Voting", f"{p.alarm_voting} alarm / {p.action_voting} executive action",
                        "1ooN for alarm gives sensitivity; 2ooN (confirmed fire/gas) for executive action avoids "
                        "spurious trips but needs more detectors to achieve coverage (ISA B.5.1-15, EGPC §8.3.1, "
                        "definition of 'Confirmed fire').",
                        "التصويت 1ooN للإنذار يعطي حساسية عالية، و2ooN (حريق/غاز مؤكد) للإجراءات التنفيذية يمنع "
                        "الإيقاف الكاذب لكنه يحتاج كواشف أكثر لتحقيق نفس التغطية (EGPC §8.3.1).",
                        "EGPC §8.3; ISA B.5.1"))
    out.append(Decision("Point gas set points", f"{p.point_alarm_pct:g} % LEL alarm / {p.point_action_pct:g} % LEL action",
                        "EGPC Table A2 / API RP 14C: alarm <= 25 % LEL, automatic action <= 60 % LEL; not lower than "
                        "5 % (methane), 10 % (propane), 20 % (gasoline) to avoid false alarms (EGPC §8.3.2).",
                        "طبقاً لجدول EGPC A2: إنذار ≤ 25% LEL وإجراء تلقائي ≤ 60% LEL، وبحد أدنى 5% للميثان و10% للبروبان "
                        "و20% للجازولين لتجنب الإنذارات الكاذبة (EGPC §8.3.2).", "EGPC §8.3.2, Table A2"))
    out.append(Decision("Open-path set points", f"{p.opgd_alarm_lelm:g} / {p.opgd_action_lelm:g} LEL.m",
                        "EGPC Table A2: 1.25 LEL.m alarm and 3.0 LEL.m action are equivalent to 25 % / 60 % LEL "
                        "over a 5 m cloud.",
                        "جدول EGPC A2: ‏1.25 LEL.m للإنذار و3.0 LEL.m للإجراء تكافئ 25%/60% LEL على سحابة 5 م.",
                        "EGPC Table A2"))
    out.append(Decision("Graded volume extent", f"{p.graded_buffer_m:g} m around major equipment",
                        "EGPC §8.2.2.1: there is no clear way to define the graded volume; it is recommended to "
                        "extend at least 2 m around each major equipment item.",
                        "EGPC §8.2.2.1: يوصى بمد الحجم المُصنّف 2 م على الأقل حول كل معدة رئيسية.",
                        "EGPC §8.2.2.1"))
    if p.apply_egpc_relaxation:
        out.append(Decision("Acceptance criterion for A*/A", ">= 80 % coverage",
                            "EGPC §8.5 note and Annex C: although grade calculations may require >= 90 %, achieving it "
                            "is practically and economically difficult; >= 80 % is acceptable for A* and A grades.",
                            "ملاحظة EGPC §8.5: رغم أن الحسابات قد تتطلب 90%، فإن تحقيق ذلك صعب عملياً واقتصادياً؛ لذلك "
                            "يُقبل 80% كحد أدنى لدرجات A* و A.", "EGPC §8.5"))
    out.append(recommend_method(project))
    ign = project.d3d_settings.get("ignition_for_gas", True)
    out.append(Decision("Ignition adjustment for flammable gas rank", "Applied" if ign else "Not applied",
                        "EGPC Annex C Step 7 text omits the ignition adjustment for flammable gas, whereas EGPC "
                        "Figure 2 and ISA Annex A.3 include it. "
                        + ("The flowchart/ISA interpretation is used." if ign else
                           "The Step 7 text interpretation (more conservative) is used."),
                        "نص EGPC Annex C Step 7 لا يُدخل تعديل الاشتعال في رتبة الغاز، بينما مخطط Figure 2 و ISA A.3 "
                        "يُدخلانه. " + ("تم اتباع المخطط/ISA." if ign else "تم اتباع النص (الأكثر تحفظاً)."),
                        "EGPC Annex C; ISA A.3"))
    if info.phase == "existing":
        out.append(Decision("Existing facility optimisation order", "Re-aim -> small move -> add",
                            "EGPC §7.2: change flame detector angles first, then small moves within cable slack, then "
                            "add new detectors rather than multiple relocations.",
                            "EGPC §7.2: تعديل زوايا كواشف اللهب أولاً، ثم تحريك بسيط في حدود الكابل، ثم إضافة كواشف "
                            "جديدة بدلاً من نقل عدة كواشف.", "EGPC §7.2"))
    return out


def all_decisions(project: Project) -> list[Decision]:
    out = philosophy_decisions(project)
    for z in project.zones:
        out += zone_decisions(project, z)
    for d in project.decisions:  # user-recorded
        out.append(Decision(d.topic, d.choice, d.why, d.why, d.ref or "Engineering judgement", d.zone))
    return out
