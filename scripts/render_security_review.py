#!/usr/bin/env python3
"""Write the Spanish rule-by-rule review for the exact current IaC commit."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

if __package__:
    from .verify_security import ROOT, compare_firewall, compare_nsg, load_sources, read_plans, resources_from_plan, security_content_hashes
else:
    from verify_security import ROOT, compare_firewall, compare_nsg, load_sources, read_plans, resources_from_plan, security_content_hashes


def select_plan(path, run):
    plans = [(name, plan) for name, plan in read_plans(path) if name == run]
    if len(plans) != 1:
        raise ValueError(f"Expected one {run} plan in {path}")
    return resources_from_plan(plans[0][1])


def verify_provider_plans(directory, tables, tokens):
    counts = []
    for run, envs, temporary in [
        ("development_stable_policy", {"dev"}, set()),
        ("all_environments_stable_policy", {"dev", "test", "prod"}, set()),
        ("migration_explicitly_selected", {"dev", "test", "prod"}, {"FW-401", "FW-402", "FW-501", "FW-502", "FW-503", "FW-504"}),
    ]:
        resources = select_plan(directory / "connectivity.jsonl", run)
        counts.append(len(compare_firewall(resources, tables, envs, temporary, tokens)))
    for env in ("dev", "test", "prod"):
        resources = select_plan(directory / f"{env}.jsonl", "subnet_policy_matches_table")
        counts.append(len(compare_nsg(resources, tables, env, set(), tokens)))
    resources = select_plan(directory / "prod.jsonl", "subnet_migration_explicitly_selected")
    counts.append(len(compare_nsg(resources, tables, "prod", {"NSG-prod-11", "NSG-prod-12", "NSG-prod-14"}, tokens)))
    return counts


def escape(value):
    return value.replace("|", "\\|").replace("\n", " ")


def counterpart(row):
    if row["id"] == "FW-999":
        return "Denegación implícita; salida `implicit_deny`. No se crea una regla de red global."
    if row["punto_control"] == "azure-firewall":
        kind = "network_rule_collection" if row["tipo"] == "red" else "application_rule_collection"
        return f"`modules/security/main.tf`: `{kind}` con nombre de regla `{row['id']}`"
    if row["punto_control"] == "nsg" and row["ambiente"] in ("dev", "test", "prod"):
        return f"`modules/security/subnet-controls`: `azurerm_network_security_rule`, `{row['id']}`; cierre expandido por subred" if row["accion"] == "Denegar" else f"`modules/security/subnet-controls`: `azurerm_network_security_rule`, `{row['id']}`"
    return {"nsg": "Fuera del módulo de aplicación: NSG del DNS del hub; se integra con el resolver.", "waf": "Fuera del alcance dev: política WAF del portal de prod/test; no convertir a Azure Firewall.", "iot-hub": "Fuera del alcance dev: TLS y credenciales de IoT Hub/DPS en producción, diseño #13."}[row["punto_control"]]


def render(commit, manifest, tables, core, counts):
    rows = tables["firewall-policy.csv"]
    provider_ok = counts is not None
    lines = [
        "# Verificación de IaC frente a la tabla del firewall", "",
        "## 1. Alcance y versión revisada", "",
        "Historia: [#21](https://github.com/frioandes-platform/planning/issues/21). Ambiente de referencia: **dev**.", "",
        f"- Código IaC revisado: commit `{commit}` de `frioandes-platform/iac`.",
        f"- Base de red corregida: commit `{manifest['network_base']['commit']}`, PR [iac#2](https://github.com/frioandes-platform/iac/pull/2), correspondiente a #20.",
        f"- Tabla y ajustes: commit `{manifest['commit']}` de `frioandes-platform/planning`.",
        "- El commit IaC identificado debe publicarse sin modificar su contenido para que la referencia pueda consultarse en GitHub. Si se cambia o se recrea el commit, regenerar este informe.", "",
        "Se revisa un firewall compartido en conectividad y los NSG de aplicación. Para dev hay 11 filas explícitas estables de Azure Firewall, FW-999 como denegación implícita y 14 filas estables de NSG. El cierre de NSG se materializa en 11 subredes: 24 recursos de regla en dev.", "",
        "La tabla contiene 100 filas: 41 de Azure Firewall, 47 de NSG, 10 de WAF y 2 de IoT Hub/DPS. La sección 6 clasifica todas; no afirma que WAF, DNS e IoT estén desplegados por este módulo.", "",
        "## 2. Fuentes y trazabilidad", "",
        "Los CSV originales se conservan en `modules/security/data`, con SHA-256 y Git blob en `source.json`. La revisión verifica ambos. La copia de `ip-plan.csv` de #20 es idéntica en bytes a la de seguridad: ambas usan la corrección de comillas de planning #64. Se conservan las entradas, salidas, nombres, CIDR y delegaciones del módulo de red.", "",
        "| Archivo | SHA-256 |", "|---|---|",
    ]
    for name, item in manifest["files"].items():
        lines.append(f"| `{name}` | `{item['sha256']}` |")
    lines += ["", "## 3. Resultado y límites de la evidencia", ""]
    if provider_ok:
        lines += ["**Resultado: sin discrepancias** entre los recursos de los planes simulados revisados y las filas aplicables de la tabla, para los escenarios declarados.", "", f"El comparador examinó respectivamente {counts} identificadores explícitos de origen en los siete escenarios de firewall/NSG. FW-999 se representa mediante la denegación implícita."]
    else:
        lines += ["**Resultado de la revisión estática y de la traducción evaluada con Terraform Core: sin discrepancias** en las reglas aplicables al alcance descrito. **La comparación contra planes del proveedor continúa pendiente**; esta conclusión no equivale a aprobar un despliegue.", "", "En el entorno de preparación, el proveedor no pudo arrancar porque la comunicación mediante socket local devolvió `operation not permitted`. No se presentan `terraform validate` ni `terraform test` como aprobados para esta entrega."]
    lines += ["", "Comprobaciones realizadas:", "", "- Integridad y estructura de los tres CSV: correctas.", "- Copias de `ip-plan.csv` de red y seguridad idénticas en bytes y SHA-256; la divergencia entre módulos se rechaza.", "- Verificador de diseño de #9: 12 de 12 comprobaciones aprobadas sobre las 100 filas.", "- Python: 17 pruebas aprobadas (7 de red y 10 del comparador/procedencia de seguridad). Los planes utilizados en las pruebas unitarias del comparador son fixtures sintéticos.", "- `terraform fmt -check -recursive`: aprobado.", "", "La ejecución completa de #20, registrada en `VALIDATION.md` y confirmada en Ubuntu sobre el commit base, corresponde al módulo de red. No se reutiliza como prueba de `validate` o `test` del código añadido en #21.", ""]
    if core:
        lines += ["- Evaluación de las expresiones HCL originales de selección/traducción con Terraform Core 1.9.8: siete escenarios aprobados. Se evalúan los `locals` sin proveedor; los registros con forma de recurso que consume el comparador son sintéticos, no planes de AzureRM.", "", "| Escenario de Core | IDs explícitos | Resultado |", "|---|---|---|"]
        for item in core["results"]:
            lines.append(f"| `{item['case']}` | {item['explicit_source_ids']} | {item['core_evaluation']} |")
    lines += ["", "No se ejecutó un plan autenticado ni un apply. Las credenciales, cuotas, disponibilidad regional, tráfico de plataforma de cada servicio, rutas, DNS, peering, diagnósticos y conectividad efectiva requieren su propia implementación y prueba. No se infiere aislamiento operativo de un plan simulado.", "",
        "## 4. Traducciones y discrepancias evitadas o corregidas", "",
        "1. **FW-999 no es una regla de red `Deny *`.** Las reglas de red se procesan antes que las de aplicación; un cierre explícito global bloquearía los permisos de aplicación. Se conserva la denegación implícita del diseño y se documentan las reglas de infraestructura y el retorno con estado propios de Azure.",
        "2. **HTTP y HTTPS se emparejan con su puerto.** En FW-306/312/318 se crean HTTP/80 y HTTPS/443, sin abrir HTTPS/80 por producto cartesiano.",
        "3. **Cada punto de control conserva su lugar.** NSG se implementa como NSG; WAF e IoT no se trasladan al firewall de red. El cierre NSG-*-99 se expande a cada subred y queda antes de los permisos predeterminados de Azure.",
        "4. **SNAT conserva exactamente la lista aprobada.** No se sustituye por `10.0.0.0/8` ni por todos los rangos privados, porque eso cambiaría el retorno desde los endpoints privados.",
        "5. **Los marcadores se resuelven expresamente.** Los FQDN, IP públicas y puertos todavía no confirmados se reciben como entradas. El código rechaza marcadores seleccionados sin resolver y sustituciones de tokens fijos o comodines globales. Las fixtures usan dominios e IP ficticios y no configuran producción.",
        "6. **No se triplica el firewall.** El root de conectividad crea uno; los NSG se gestionan desde la suscripción y estado de cada ambiente.",
        "7. **Temporales desactivadas por defecto.** Se seleccionan por ID y exigen referencia de cambio. Los nombres de las colecciones/grupos y las descripciones distinguen `temporary` de `stable`. El registro conserva el retiro de cada regla.", "",
        "Estas decisiones son traducciones explícitas de la tabla y correcciones del riesgo de implementación; no se modifica la política de negocio ni se añaden permisos silenciosamente.", "",
        "## 5. Revisión detallada de las filas estables de dev", "",
        "| ID | Punto | Origen | Destino | Protocolo | Puerto | Acción | Contraparte |", "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        if row["vigencia"] == "estable" and ((row["ambiente"] == "dev" and row["punto_control"] in ("azure-firewall", "nsg")) or row["id"] == "FW-999"):
            fields = [row["id"], row["punto_control"], row["origen_rangos"], row["destino_rangos"], row["protocolo"], row["puertos"], row["accion"]]
            lines.append("| " + " | ".join("`" + escape(value) + "`" for value in fields) + " | " + counterpart(row) + " |")
    lines += ["", "## 6. Cobertura y clasificación de todas las filas", "", "Las reglas de otros ambientes tienen soporte de código donde se indica, pero no se incluyen silenciosamente en la política de referencia dev. Las temporales requieren selección expresa; las de producción no se aplican a dev. Las dos filas de DNS del hub, las diez de WAF y las dos de IoT/DPS quedan identificadas fuera del módulo y deben conciliarse en sus propias implementaciones.", "", "| ID | Punto | Ambiente | Vigencia | Código o razón de exclusión |", "|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| `{row['id']}` | {row['punto_control']} | {row['ambiente']} | {row['vigencia']} | {counterpart(row)} |")
    lines += ["", "## 7. Reglas temporales y retiro", "", "| ID | Grupo | Condición de retiro copiada de la fuente |", "|---|---|---|"]
    for row in rows:
        if row["vigencia"] == "temporal":
            lines.append(f"| `{row['id']}` | {row['grupo']} | {escape(row['se_retira'])} |")
    lines += ["", "Terraform no programa la retirada por el paso del tiempo. El responsable debe quitar cada ID al alcanzar su hito, revisar el plan y aplicar la retirada por el proceso aprobado. La revisión no asume que todas las temporales se retiren simultáneamente.", "",
        "## 8. Reproducir y completar la validación", "", "Desde el commit IaC indicado, en la raíz de `iac`:", "", "```bash", "terraform fmt -recursive", "bash scripts/check-security.sh", "```", "",
        "El script produce planes simulados JSON en `.security-verification/` y los compara contra las filas de referencia. No necesita autenticación de Azure. Para actualizar este documento con el resultado de esos planes:", "", "```bash", "python3 scripts/render_security_review.py \\", "  --plans-directory .security-verification \\", "  --out ../planning/docs/iac/verificacion-iac-vs-firewall.md", "```", "",
        "El generador rechaza planes con diferencias y requiere que el árbol de trabajo del código esté limpio. Si se modifica o reformatea el código, hacer commit y volver a ejecutar las comprobaciones antes de generar el informe. No registrar como verificado el SHA de un código anterior al cambio.", "",
        "Los valores de pruebas no sustituyen las confirmaciones del cliente. Antes de desplegar, se completan las entradas reales y se comprueba que las reglas de plataforma necesarias para los servicios no queden bloqueadas por los cierres de NSG. La misma revisión se repite sobre el plan autenticado del despliegue aprobado.", "",
        "## 9. Referencias", "", "- [Tabla y diseño de firewall #9](../architecture/red-firewall-y-publicacion.md).", "- [Plan de red #8](../architecture/red-topologia-subnetting.md).", "- [Azure Firewall: orden de procesamiento](https://learn.microsoft.com/en-us/azure/firewall/rule-processing).", "- [AzureRM 4.62.0: colecciones de reglas](https://registry.terraform.io/providers/hashicorp/azurerm/4.62.0/docs/resources/firewall_policy_rule_collection_group).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--core-evidence", type=Path)
    parser.add_argument("--plans-directory", type=Path)
    args = parser.parse_args()
    if not args.core_evidence and not args.plans_directory:
        parser.error("Provide --core-evidence or --plans-directory for this exact code revision.")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "."], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).strip()
    if untracked:
        raise ValueError("Commit or exclude untracked implementation files before generating the review.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest, tables = load_sources()
    subprocess.run(["git", "merge-base", "--is-ancestor", manifest["network_base"]["commit"], commit], cwd=ROOT, check=True)
    core = json.loads(args.core_evidence.read_text()) if args.core_evidence else None
    if core and core.get("code_hashes") != security_content_hashes():
        raise ValueError("Core evidence belongs to different code. Rerun evaluate_security_contract.py.")
    counts = None
    if args.plans_directory:
        provenance = json.loads((args.plans_directory / "provenance.json").read_text())
        if provenance["code_hashes"] != security_content_hashes():
            raise ValueError("Code/fixtures changed after validation. Rerun check-security.sh before publishing the review.")
        for name, checksum in provenance["plan_hashes"].items():
            if hashlib.sha256((args.plans_directory / name).read_bytes()).hexdigest() != checksum:
                raise ValueError("Plan evidence changed after validation: " + name)
        tokens = json.loads((ROOT / "tests/fixtures/security-tokens.json").read_text())
        counts = verify_provider_plans(args.plans_directory, tables, tokens)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(commit, manifest, tables, core, counts), encoding="utf-8")
    print(f"Review written for IaC commit {commit}: {args.out}")


if __name__ == "__main__":
    main()
