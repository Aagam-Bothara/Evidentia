"""Predefined LaTeX templates for academic papers."""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "article": {
        "id": "article",
        "name": "Plain Article",
        "description": "Standard LaTeX article — suitable for general-purpose papers",
        "category": "General",
        "preamble": (
            "\\documentclass[12pt]{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{natbib}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n"
            "\\author{{}}\n"
            "\\date{{\\today}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Methods}}\n\n\n"
            "\\section{{Results}}\n\n\n"
            "\\section{{Discussion}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{plainnat}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "ieee_conference": {
        "id": "ieee_conference",
        "name": "IEEE Conference",
        "description": "IEEE two-column conference format — ICS, S&P, CCS, INFOCOM, etc.",
        "category": "IEEE",
        "preamble": (
            "\\documentclass[conference]{IEEEtran}\n"
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb,amsfonts}\n"
            "\\usepackage{algorithmic}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{textcomp}\n"
            "\\usepackage{xcolor}\n"
            "\\usepackage{hyperref}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n"
            "\\author{{\n"
            "  \\IEEEauthorblockN{{Author Name}}\n"
            "  \\IEEEauthorblockA{{\n"
            "    Department \\\\\n"
            "    University \\\\\n"
            "    email@example.com\n"
            "  }}\n"
            "}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\begin{{IEEEkeywords}}\n"
            "keyword1, keyword2, keyword3\n"
            "\\end{{IEEEkeywords}}\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Methodology}}\n\n\n"
            "\\section{{Evaluation}}\n\n\n"
            "\\section{{Discussion}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{IEEEtran}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "ieee_journal": {
        "id": "ieee_journal",
        "name": "IEEE Journal / Transactions",
        "description": "IEEE journal format — TDSC, TIFS, TPAMI, etc.",
        "category": "IEEE",
        "preamble": (
            "\\documentclass[journal]{IEEEtran}\n"
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb,amsfonts}\n"
            "\\usepackage{algorithmic}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{textcomp}\n"
            "\\usepackage{xcolor}\n"
            "\\usepackage{hyperref}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n"
            "\\author{{Author~Name,~\\IEEEmembership{{Member,~IEEE}}\n"
            "  \\thanks{{Manuscript received ...}}\n"
            "}}\n\n"
            "\\markboth{{Journal Name, Vol. XX, No. XX, Month Year}}\n"
            "{{Author: Short Title}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\begin{{IEEEkeywords}}\n"
            "keyword1, keyword2, keyword3\n"
            "\\end{{IEEEkeywords}}\n\n"
            "\\section{{Introduction}}\n"
            "\\IEEEPARstart{{T}}{{his}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{System Model}}\n\n\n"
            "\\section{{Proposed Approach}}\n\n\n"
            "\\section{{Experimental Results}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{IEEEtran}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "acm_conference": {
        "id": "acm_conference",
        "name": "ACM Conference (acmart)",
        "description": "ACM sigconf format — CHI, SIGCOMM, KDD, SIGGRAPH, etc.",
        "category": "ACM",
        "preamble": (
            "\\documentclass[sigconf,review]{acmart}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{booktabs}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n\n"
            "\\author{{Author Name}}\n"
            "\\email{{author@example.com}}\n"
            "\\affiliation{{\n"
            "  \\institution{{University}}\n"
            "  \\city{{City}}\n"
            "  \\country{{Country}}\n"
            "}}\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\begin{{CCSXML}}\n"
            "<!-- CCS concepts XML here -->\n"
            "\\end{{CCSXML}}\n\n"
            "\\keywords{{keyword1, keyword2, keyword3}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Design}}\n\n\n"
            "\\section{{Evaluation}}\n\n\n"
            "\\section{{Discussion}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{ACM-Reference-Format}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "acm_journal": {
        "id": "acm_journal",
        "name": "ACM Journal (acmart)",
        "description": "ACM journal/magazine format — TOCHI, CACM, TOPLAS, etc.",
        "category": "ACM",
        "preamble": (
            "\\documentclass[acmlarge,review]{acmart}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{booktabs}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n\n"
            "\\author{{Author Name}}\n"
            "\\email{{author@example.com}}\n"
            "\\affiliation{{\n"
            "  \\institution{{University}}\n"
            "  \\city{{City}}\n"
            "  \\country{{Country}}\n"
            "}}\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\keywords{{keyword1, keyword2, keyword3}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Background}}\n\n\n"
            "\\section{{Approach}}\n\n\n"
            "\\section{{Evaluation}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{ACM-Reference-Format}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "springer_lncs": {
        "id": "springer_lncs",
        "name": "Springer LNCS",
        "description": "Springer Lecture Notes in Computer Science — ESORICS, ACSAC, FC, etc.",
        "category": "Springer",
        "preamble": (
            "\\documentclass[runningheads]{llncs}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{booktabs}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n"
            "\\titlerunning{{Abbreviated Title}}\n\n"
            "\\author{{Author Name\\inst{{1}}}}\n"
            "\\authorrunning{{A. Name}}\n"
            "\\institute{{University, City, Country \\\\\n"
            "\\email{{author@example.com}}}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n\n"
            "\\keywords{{keyword1 \\and keyword2 \\and keyword3}}\n"
            "\\end{{abstract}}\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Background}}\n\n\n"
            "\\section{{Proposed Approach}}\n\n\n"
            "\\section{{Evaluation}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{splncs04}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "elsevier": {
        "id": "elsevier",
        "name": "Elsevier Journal",
        "description": "Elsevier two-column journal format — Computers & Security, FGCS, etc.",
        "category": "Elsevier",
        "preamble": (
            "\\documentclass[review,3p,twocolumn]{elsarticle}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{booktabs}\n"
            "\\usepackage{lineno}\n\n"
        ),
        "skeleton": (
            "\\journal{{Journal Name}}\n\n"
            "\\begin{{document}}\n\n"
            "\\begin{{frontmatter}}\n"
            "\\title{{{title}}}\n\n"
            "\\author[inst1]{{Author Name}}\n"
            "\\ead{{author@example.com}}\n"
            "\\address[inst1]{{Department, University, City, Country}}\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\begin{{keyword}}\n"
            "keyword1 \\sep keyword2 \\sep keyword3\n"
            "\\end{{keyword}}\n"
            "\\end{{frontmatter}}\n\n"
            "\\linenumbers\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Methodology}}\n\n\n"
            "\\section{{Results}}\n\n\n"
            "\\section{{Discussion}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{elsarticle-num}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "usenix": {
        "id": "usenix",
        "name": "USENIX Security / OSDI",
        "description": "USENIX conference format — USENIX Security, OSDI, NSDI, ATC, etc.",
        "category": "USENIX",
        "preamble": (
            "\\documentclass[letterpaper,twocolumn,10pt]{article}\n"
            "\\usepackage{usenix-2019-v3}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{booktabs}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n\n"
            "\\author{{\n"
            "  \\rm Author Name \\\\\n"
            "  University\n"
            "}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Background}}\n\n\n"
            "\\section{{Threat Model}}\n\n\n"
            "\\section{{Design}}\n\n\n"
            "\\section{{Implementation}}\n\n\n"
            "\\section{{Evaluation}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{plain}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "nature": {
        "id": "nature",
        "name": "Nature-style",
        "description": "Nature / Nature Communications style — single column, methods at end",
        "category": "Nature",
        "preamble": (
            "\\documentclass[12pt]{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{natbib}\n"
            "\\usepackage{setspace}\n"
            "\\doublespacing\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n"
            "\\author{{Author Name$^{{1}}$}}\n"
            "\\date{{}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "$^{{1}}$Department, University, City, Country\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here (max 150 words for Nature, 200 for Nat. Comms).\n"
            "\\end{{abstract}}\n\n"
            "\\section*{{Introduction}}\n\n\n"
            "\\section*{{Results}}\n\n\n"
            "\\section*{{Discussion}}\n\n\n"
            "\\section*{{Methods}}\n\n\n"
            "\\section*{{Data Availability}}\n\n\n"
            "\\section*{{Acknowledgements}}\n\n\n"
            "\\bibliographystyle{{naturemag}}\n"
            "\\bibliography{{references}}\n\n"
            "\\end{{document}}\n"
        ),
    },
    "arxiv_preprint": {
        "id": "arxiv_preprint",
        "name": "arXiv Preprint",
        "description": "Clean single-column preprint style for arXiv submissions",
        "category": "General",
        "preamble": (
            "\\documentclass[11pt]{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{amsmath,amssymb,amsthm}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{natbib}\n"
            "\\usepackage{algorithm}\n"
            "\\usepackage{algorithmic}\n"
            "\\usepackage{booktabs}\n\n"
        ),
        "skeleton": (
            "\\title{{{title}}}\n"
            "\\author{{\n"
            "  Author Name \\\\\n"
            "  University \\\\\n"
            "  \\texttt{{email@example.com}}\n"
            "}}\n"
            "\\date{{\\today}}\n\n"
            "\\begin{{document}}\n"
            "\\maketitle\n\n"
            "\\begin{{abstract}}\n"
            "Your abstract here.\n"
            "\\end{{abstract}}\n\n"
            "\\section{{Introduction}}\n\n\n"
            "\\section{{Preliminaries}}\n\n\n"
            "\\section{{Proposed Method}}\n\n\n"
            "\\section{{Experiments}}\n\n\n"
            "\\section{{Related Work}}\n\n\n"
            "\\section{{Conclusion}}\n\n\n"
            "\\bibliographystyle{{plainnat}}\n"
            "\\bibliography{{references}}\n\n"
            "\\appendix\n"
            "\\section{{Supplementary Material}}\n\n\n"
            "\\end{{document}}\n"
        ),
    },
}


def get_template(template_id: str) -> dict | None:
    """Get a template by ID."""
    return TEMPLATES.get(template_id)


def list_templates() -> list[dict]:
    """List all templates with metadata (no preamble/skeleton for listing)."""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "category": t["category"],
        }
        for t in TEMPLATES.values()
    ]


def render_template(template_id: str, title: str = "Untitled") -> str:
    """Render a full document from a template with the given title."""
    tmpl = TEMPLATES.get(template_id)
    if not tmpl:
        tmpl = TEMPLATES["article"]
    return tmpl["preamble"] + tmpl["skeleton"].format(title=title)
