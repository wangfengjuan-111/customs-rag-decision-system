"""
GIR（General Rules of Interpretation）常量表。
文本取自 HTS 2026 Revision 21, General Notes GN p.1-2（data/raw/general_notes.pdf），
规则条数为国际通用固定文本。Stage4/5/6 的 prompt 显式引用。

summarize 供 LLM prompt 使用（省 token），full_text 供引用溯源。
"""

GIR: dict[str, dict] = {
    "GIR1": {
        "summary": "Classification is determined by the terms of the headings and any relative section or chapter notes; the title indexes are for reference only.",
        "full_text": (
            "1. The table of contents, alphabetical index, and titles of sections, chapters and sub-chapters "
            "are provided for ease of reference only; for legal purposes, classification shall be determined "
            "according to the terms of the headings and any relative section or chapter notes and, provided such "
            "headings or notes do not otherwise require, according to the following provisions:"
        ),
    },
    "GIR2a": {
        "summary": "A heading reference to an article includes incomplete/unfinished articles having the essential character of the complete article, and complete articles entered unassembled.",
        "full_text": (
            "2. (a) Any reference in a heading to an article shall be taken to include a reference to that article "
            "incomplete or unfinished, provided that, as entered, the incomplete or unfinished article has the "
            "essential character of the complete or finished article. It shall also include a reference to that "
            "article complete or finished (or falling to be classified as complete or finished by virtue of this "
            "rule), entered unassembled or disassembled."
        ),
    },
    "GIR2b": {
        "summary": "A heading reference to a material includes mixtures with other materials; mixed-substance goods go to rule 3.",
        "full_text": (
            "2. (b) Any reference in a heading to a material or substance shall be taken to include a reference to "
            "mixtures or combinations of that material or substance with other materials or substances. Any "
            "reference to goods of a given material or substance shall be taken to include a reference to goods "
            "consisting wholly or partly of such material or substance. The classification of goods consisting of "
            "more than one material or substance shall be according to the principles of rule 3."
        ),
    },
    "GIR3": {
        "summary": "When goods are prima facie classifiable under two or more headings: (a) most specific description prevails; (b) composite goods classified by essential character; (c) last heading in numerical order as residual.",
        "full_text": (
            "3. When, by application of rule 2(b) or for any other reason, goods are, prima facie, classifiable "
            "under two or more headings, classification shall be effected as follows: (a) The heading which "
            "provides the most specific description shall be preferred to headings providing a more general "
            "description... (b) Mixtures, composite goods consisting of different materials or made up of different "
            "components, and goods put up in sets for retail sale shall be classified as if they consisted of the "
            "material or component which gives them their essential character... (c) When goods cannot be "
            "classified by reference to 3(a) or 3(b), they shall be classified under the heading which occurs last "
            "in numerical order among those which equally merit consideration."
        ),
    },
    "GIR4": {
        "summary": "Goods not otherwise specified are classifiable under the heading appropriate to goods of the same kind.",
        "full_text": (
            "4. Goods which cannot be classified in accordance with the above rules shall be classified under the "
            "heading appropriate to goods of the same kind, nature or purpose."
        ),
    },
    "GIR5": {
        "summary": "Camera/instrument cases and packaging (except packaging giving the whole its essential character) classify with the contained goods.",
        "full_text": (
            "5. In addition to the foregoing provisions, the following Rules shall apply in respect of the goods "
            "referred to therein: (a) Camera cases, musical instrument cases, gun cases, drawing instrument cases, "
            "necklace cases and similar containers... shall be classified with the articles when suitable for "
            "long-term use and presented with the articles; (b) packing materials and packing containers presented "
            "with the goods shall be classified with the goods if they are of a kind normally used for packing such "
            "goods, unless clearly suitable for repetitive use."
        ),
    },
    "GIR6": {
        "summary": "Subheading-level analog of GIR 1-5: comparison at subheading level within the same heading, subheading notes apply, only one-subheading comparison determinations.",
        "full_text": (
            "6. For legal purposes, the classification of goods in the subheadings of a heading shall be determined "
            "according to the terms of those subheadings and any related subheading notes and, mutatis mutandis, "
            "to the above Rules, on the understanding that only subheadings at the same level are comparable."
        ),
    },
}

# Stage4 排除降级与具体列名裁决最常用的三条
CORE_RULES = ["GIR1", "GIR3", "GIR6"]
