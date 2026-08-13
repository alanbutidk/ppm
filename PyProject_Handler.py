"""
pyproject handler for ppm.
Copyright (c) 2026 Alan. All Rights Reserved.
"""

from TOMLFile_Helper import TOMLDocument, TOMLTable


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
    pt.add("description", ppmConfig.get("requires_python", ">=3.10"))
    pt.add("readme", "README.md")
    pt.add("license", {"text": ppmConfig.get("license", "GPL-3.0-Only")})
    pt.add("authors", [{"name": ppmConfig.get("author_name", "ppm_user")}])

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
    ppm_tool.add("version", "2.0.0")
    doc.add_table(ppm_tool)

    with open("pyproject.toml", "w", encoding="utf-8") as f:
        f.write(doc.render(dontwrite_dontedit=False))
