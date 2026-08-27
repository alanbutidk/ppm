"""
pyproject handler for ppm.
Copyright (c) 2026 Alan. All Rights Reserved.
"""

from TOMLFile_Helper import TOMLDocument, TOMLTable

SPDX_LICENSES_MAPPING = {
    "CC0-1.0": "Creative Commons Zero v1.0 Universal",
    "Unlicense": "The Unlicense",
    "0BSD": "BSD Zero Clause License",
    "WTFPL": "Do What The F*** You Want To Public License",
    "MIT": "MIT License",
    "MIT-0": "MIT No Attribution",
    "MIT-Modern-Variant": "MIT Modern Variant",
    "BSD-2-Clause": "BSD 2-Clause 'Simplified' License",
    "BSD-3-Clause": "BSD 3-Clause 'New' or 'Modified' License",
    "BSD-3-Clause-Clear": "BSD 3-Clause Clear License",
    "BSD-4-Clause": "BSD 4-Clause 'Original' or 'Old' License",
    "Apache-1.0": "Apache License 1.0",
    "Apache-1.1": "Apache License 1.1",
    "Apache-2.0": "Apache License 2.0",
    "GPL-1.0-only": "GNU General Public License v1.0 only",
    "GPL-1.0-or-later": "GNU General Public License v1.0 or later",
    "GPL-2.0-only": "GNU General Public License v2.0 only",
    "GPL-2.0-or-later": "GNU General Public License v2.0 or later",
    "GPL-3.0-only": "GNU General Public License v3.0 only",
    "GPL-3.0-or-later": "GNU General Public License v3.0 or later",
    "LGPL-2.0-only": "GNU Library General Public License v2 only",
    "LGPL-2.0-or-later": "GNU Library General Public License v2 or later",
    "LGPL-2.1-only": "GNU Lesser General Public License v2.1 only",
    "LGPL-2.1-or-later": "GNU Lesser General Public License v2.1 or later",
    "LGPL-3.0-only": "GNU Lesser General Public License v3.0 only",
    "LGPL-3.0-or-later": "GNU Lesser General Public License v3.0 or later",
    "AGPL-1.0-only": "Affero General Public License v1.0 only",
    "AGPL-1.0-or-later": "Affero General Public License v1.0 or later",
    "AGPL-3.0-only": "GNU Affero General Public License v3.0 only",
    "AGPL-3.0-or-later": "GNU Affero General Public License v3.0 or later",
    "MPL-1.0": "Mozilla Public License 1.0",
    "MPL-1.1": "Mozilla Public License 1.1",
    "MPL-2.0": "Mozilla Public License 2.0",
    "MPL-2.0-no-copyleft-exception": "Mozilla Public License 2.0 (no copyleft exception)",
    "EPL-1.0": "Eclipse Public License 1.0",
    "EPL-2.0": "Eclipse Public License 2.0",
    "CDDL-1.0": "Common Development and Distribution License 1.0",
    "CDDL-1.1": "Common Development and Distribution License 1.1",
    "CPL-1.0": "Common Public License 1.0",
    "CC-BY-1.0": "Creative Commons Attribution 1.0 Generic",
    "CC-BY-2.0": "Creative Commons Attribution 2.0 Generic",
    "CC-BY-3.0": "Creative Commons Attribution 3.0 Unported",
    "CC-BY-4.0": "Creative Commons Attribution 4.0 International",
    "CC-BY-SA-1.0": "Creative Commons Attribution-ShareAlike 1.0 Generic",
    "CC-BY-SA-2.0": "Creative Commons Attribution-ShareAlike 2.0 Generic",
    "CC-BY-SA-3.0": "Creative Commons Attribution-ShareAlike 3.0 Unported",
    "CC-BY-SA-4.0": "Creative Commons Attribution-ShareAlike 4.0 International",
    "CC-BY-NC-4.0": "Creative Commons Attribution-NonCommercial 4.0 International",
    "CC-BY-NC-SA-4.0": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International",
    "MS-PL": "Microsoft Public License",
    "MS-RL": "Microsoft Reciprocal License",
    "ISC": "ISC License",
    "AFL-1.1": "Academic Free License v1.1",
    "AFL-2.0": "Academic Free License v2.0",
    "AFL-3.0": "Academic Free License v3.0",
    "Artistic-1.0": "Artistic License 1.0",
    "Artistic-2.0": "Artistic License 2.0",
    "PostgreSQL": "PostgreSQL License",
    "Python-2.0": "Python License 2.0",
    "Zlib": "zlib License",
}


def GenFullPyProject(ppmConfig: dict):
    """
    Generate a full pyproject.toml using the setuptools build backend
    Uses PEP 621 metadata, fully compatible with pip, poetry and uv.
    """
    doc = TOMLDocument()
    BuildSys = TOMLTable("build-system")
    BuildSys.add("requires", ["setuptools>=61.0", "wheel"])
    BuildSys.add("build-backend", "setuptools.build_meta")
    doc.add_table(BuildSys)

    pt = TOMLTable("project")
    pt.add("name", ppmConfig["name"])
    pt.add("version", ppmConfig["version"])
    pt.add("description", ppmConfig.get("description", ""))
    pt.add("requires-python", ppmConfig.get("requires_python", ">=3.10"))
    pt.add("readme", "README.md")
    pt.add("license", ppmConfig.get("license", "GPL-3.0-only"))
    pt.add("authors", [{"name": ppmConfig.get("author_name", "ppm_user")}])
    custom_lic = ppmConfig.get("CustomLicense", None)

    if custom_lic:
        # SPDX PEP 639 norms custom license formatting
        pt.add("license", f"LicenseRef-{custom_lic}")
        pt.add("license-files", ["LICENSE*", "LICENCE*"])
    else:
        provided_lic = ppmConfig.get("license", "GPL-3.0-only")
        matched_license = next(
            (k for k in SPDX_LICENSES_MAPPING if k.lower() == provided_lic.lower()),
            "GPL-3.0-only",
        )
        pt.add("license", {"text": matched_license})

    deps_list = [
        f"{pkg}{ver}" for pkg, ver in ppmConfig.get("dependencies", {}).items()
    ]
    pt.add("dependencies", deps_list)
    doc.add_table(pt)

    deps_list = [
        f"{pkg}{ver}" for pkg, ver in ppmConfig.get("dependencies", {}).items()
    ]
    pt.add("dependencies", deps_list)
    doc.add_table(pt)

    if "scripts" in ppmConfig:
        ptScripts = TOMLTable("project.scripts")
        for cmdName, mdlePath in ppmConfig["scripts"].items():
            ptScripts.add(cmdName, mdlePath)
        doc.add_table(ptScripts)

    sCfg = TOMLTable("tool.setuptools.packages.find")
    sCfg.add("where", ["."])
    sCfg.add("include", [ppmConfig["name"].replace("-", "_") + "*"])
    doc.add_table(sCfg)

    poetry = TOMLTable("tool.poetry")
    poetry.add("name", ppmConfig["name"])
    poetry.add("version", ppmConfig["version"])
    poetry.add("description", ppmConfig.get("description", ""))
    doc.add_table(poetry)

    ppm_tool = TOMLTable("tool.ppm")
    ppm_tool.add("managed-by", "ppm-cli")
    ppm_tool.add("version", "3.0.0")
    doc.add_table(ppm_tool)

    with open("pyproject.toml", "w", encoding="utf-8") as f:
        f.write(doc.render(dontwrite_dontedit=False))
