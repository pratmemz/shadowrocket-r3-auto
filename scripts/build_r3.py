#!/usr/bin/env python3
"""Rebuild R3 over the newest Johnshall sr_cnip.conf. No third-party packages.

Fail closed: if upstream's required layout/DNS or GEOIP/FINAL anchors change,
stop rather than publishing an unreviewed or potentially leaky configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = "https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip.conf"
EXPECTED_DNS = "https://dns.alidns.com/dns-query, https://doh.pub/dns-query"
R3_DNS = """# R3 stable domestic DoH: foreign proxy domains should be resolved at the proxy side.
dns-server = https://dns.alidns.com/dns-query#no-h3, https://doh.pub/dns-query#no-h3
fallback-dns-server = https://dns.alidns.com/dns-query#no-h3, https://doh.pub/dns-query#no-h3
dns-direct-system = false
proxy-dns-server = https://dns.alidns.com/dns-query#no-h3"""
HEADER = """# R3 auto-generated from Johnshall sr_cnip.conf; no node credentials included.
# Original upstream rules preserved. May not prevent every OS/application DNS leak.
# For iOS, validate compatibility and app-specific UDP behavior before everyday use.
"""

class PatchError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Shadowrocket-R3-Autosync/1.0"})
    with urllib.request.urlopen(request, timeout=25) as resp:
        raw = resp.read(1_000_001)
    if len(raw) > 1_000_000:
        raise PatchError("Upstream larger than 1MB, refuse update")
    return raw.decode("utf-8-sig")


def extract_section(source: str, name: str) -> str:
    matches = list(re.finditer(rf"(?m)^\[{re.escape(name)}\][ \t]*$", source))
    if len(matches) != 1:
        raise PatchError(f"Expected one [{name}], found {len(matches)}")
    match = matches[0]
    nxt = re.search(r"(?m)^\[[^\]\r\n]+\][ \t]*$", source[match.end():])
    if nxt:
        return source[match.end():match.end()+nxt.start()]
    return source[match.end():]


def rule_lines(source: str) -> list[str]:
    return [ln.strip() for ln in extract_section(source,"Rule").splitlines()
            if ln.strip() and not ln.lstrip().startswith(("#", ";"))]


def normalize_base_rule(line: str) -> str:
    main = re.split(r"\s+(?://|#)", line.strip(), maxsplit=1)[0]
    return main.casefold().replace(",no-resolve", "").strip()


def patch_upstream(source: str, update_url: str | None) -> str:
    if not source.endswith("\n"):
        source += "\n"
    if len(source) < 1500 or len(source) > 1_000_000:
        raise PatchError("Upstream content length unusual")
    if source.count("[General]") != 1 or source.count("[Rule]") != 1:
        raise PatchError("Unrecognized upstream sections")
    # Refuse accidental HTML/login/error content or already patched input.
    if "# ---- R3:" in source or "<!DOCTYPE" in source[:1000]:
        raise PatchError("Upstream is not the pristine source")
    gen = extract_section(source,"General")
    rules = extract_section(source,"Rule")
    other_required = ["[URL Rewrite]", "[MITM]"]
    if any(t not in source for t in other_required):
        raise PatchError("Missing expected upstream section(s)")
    src_rule_lines = rule_lines(source)
    if len(src_rule_lines) < 100:
        raise PatchError("Unexpectedly few upstream rules")
    for key in ("dns-server", "update-url", "fallback-dns-server", "dns-direct-system", "proxy-dns-server"):
        entries = [l for l in gen.splitlines() if re.match(rf"\s*{re.escape(key)}\s*=",l)]
        if key == "dns-server":
            if len(entries) != 1 or entries[0].split("=",1)[1].strip() != EXPECTED_DNS:
                raise PatchError("Upstream primary DNS changed: manual review required")
        elif key != "update-url" and entries:
            raise PatchError(f"Upstream now sets {key}; manual review required")
        elif key == "update-url" and len(entries) > 1:
            raise PatchError("Multiple upstream update-url directives")
    lines=[]
    for ln in gen.splitlines():
        if re.match(r"\s*dns-server\s*=",ln):
            lines.extend(R3_DNS.splitlines())
        elif re.match(r"\s*update-url\s*=",ln):
            continue
        else:
            lines.append(ln)
    if update_url:
        if not update_url.startswith("https://") or " " in update_url:
            raise PatchError("update-url must be HTTPS without spaces")
        lines.append("update-url = " + update_url)
    else:
        lines.append("# update-url intentionally omitted until hosted in your GitHub repository")
    new_gen="\n".join(lines).rstrip()+"\n"

    priority=(ROOT/'patches/priority_proxy.txt').read_text(encoding='utf-8').rstrip()+"\n"
    direct=(ROOT/'patches/domestic_direct.txt').read_text(encoding='utf-8').rstrip()+"\n"
    original=rules.splitlines()
    # Only accept the known two-rule tail. Changing these policies should fail closed.
    active=[(i,ln.strip()) for i,ln in enumerate(original) if ln.strip() and not ln.lstrip().startswith(("#",";"))]
    if len(active) < 100 or [v.upper() for _,v in active[-2:]] != ["GEOIP,CN,DIRECT", "FINAL,PROXY"]:
        raise PatchError("Upstream GEOIP/FINAL tail changed: manual review required")
    geo_idx,final_idx=active[-2][0],active[-1][0]
    processed=[]
    for i,ln in enumerate(original):
        if i == geo_idx:
            processed.append(direct.rstrip("\n"))
            processed.append("# Do not pre-resolve unknown domains for GEOIP classification.")
            processed.append("GEOIP,CN,DIRECT,no-resolve")
        elif i == final_idx:
            processed.append("FINAL,PROXY,dns-failed")
        elif re.match(r"\s*IP-CIDR,",ln,flags=re.IGNORECASE):
            # Only modify a PROXY IP-CIDR rule. Keep all domain rules as downloaded.
            code,sep,comment=ln.partition(" //")
            if not sep:
                # '#' is only recognized as a comment after whitespace.
                m=re.search(r"\s+#",ln)
                if m:
                    code,sep,comment=ln[:m.start()],ln[m.start():],""
                else:
                    code,sep,comment=ln,"",""
            parts=[p.strip() for p in code.split(",")]
            if len(parts)>=3 and parts[2].upper()=="PROXY" and not any(p.lower()=="no-resolve" for p in parts[3:]):
                code=code.rstrip()+",no-resolve"
            processed.append(code+sep+comment)
        else:
            processed.append(ln)
    new_rules="\n"+priority+"# ---- Original Johnshall rules follow ----\n"+"\n".join(processed).lstrip("\n").rstrip()+"\n\n"

    old_general_pattern=r"(?ms)^\[General\][ \t]*\n.*?(?=^\[Rule\][ \t]*$)"
    old_rule_pattern=r"(?ms)^\[Rule\][ \t]*\n.*?(?=^\[[^\]\r\n]+\][ \t]*$)"
    output = re.sub(old_general_pattern,lambda _:"[General]\n"+new_gen+"\n",source,count=1)
    output = re.sub(old_rule_pattern,lambda _:"[Rule]"+new_rules,output,count=1)
    output = HEADER + output
    validate(source,output,update_url)
    return output


def domain_policy(out: str, domain: str) -> str:
    """Approximate first matching domain-suffix policy for static tests."""
    for ln in rule_lines(out):
        parts=[p.strip() for p in ln.split(",")]
        if len(parts)>=3:
            typ, rule, policy=parts[:3]
            if typ.upper()=="DOMAIN-SUFFIX" and (domain==rule or domain.endswith("."+rule)):
                return policy.upper()
            if typ.upper()=="DOMAIN" and domain==rule:
                return policy.upper()
    return "PROXY" # FINAL


def validate(upstream: str, out: str, update_url: str | None) -> None:
    assert out.count("[General]")==1 and out.count("[Rule]")==1
    assert out.count("GEOIP,CN,DIRECT,no-resolve")==1
    assert out.count("FINAL,PROXY,dns-failed")==1
    assert out.count("fallback-dns-server = ")==1
    assert out.count("proxy-dns-server = ")==1
    assert out.count("dns-direct-system = false")==1
    assert sum(ln.startswith("dns-server = https://dns.alidns.com/dns-query#no-h3") for ln in out.splitlines())==1
    if update_url:
        assert sum(ln.startswith("update-url = ") for ln in out.splitlines())==1, "Unexpected duplicated update-url"
        assert f"update-url = {update_url}" in out
    # Every upstream rule retained, except only the deliberately replaced GEOIP/FINAL tail.
    original_rules=[l for l in rule_lines(upstream)
                    if l.upper() not in ("GEOIP,CN,DIRECT","FINAL,PROXY")]
    converted={normalize_base_rule(l) for l in rule_lines(out)}
    lost=[l for l in original_rules if normalize_base_rule(l) not in converted]
    if lost:
        raise PatchError("Upstream rules lost: "+repr(lost[:5]))
    for domain,policy in {
        "www.google.com":"PROXY", "www.youtube.com":"PROXY",
        "chatgpt.com":"PROXY","dns.google":"PROXY",
        "random.bufanche.com":"PROXY", "foo.dnsleaktest.com":"PROXY",
        "www.baidu.com":"DIRECT","www.qq.com":"DIRECT",
        "www.jd.com":"DIRECT","www.bilibili.com":"DIRECT",
    }.items():
        actual=domain_policy(out,domain)
        if actual!=policy:
            raise PatchError(f"Domain simulation failed: {domain} {actual}!={policy}")


def main() -> int:
    ap=argparse.ArgumentParser(description="Safely overlay the known-good R3 patch onto upstream Johnshall sr_cnip.conf")
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fetch",action="store_true",help="Read current official upstream through HTTPS")
    g.add_argument("--source",type=Path,help="Read local upstream fixture")
    ap.add_argument("--repo",help="GitHub OWNER/REPO, for self-update URL")
    ap.add_argument("--output",type=Path,default=ROOT/'sr_cnip_r3_auto.conf')
    ap.add_argument("--metadata",type=Path,default=None)
    args=ap.parse_args()
    try:
        raw=fetch_url(DEFAULT_SOURCE) if args.fetch else args.source.read_text(encoding="utf-8-sig")
        if args.repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",args.repo):
            raise PatchError("Invalid Github OWNER/REPO format")
        update_url=(f"https://raw.githubusercontent.com/{args.repo}/main/sr_cnip_r3_auto.conf" if args.repo else None)
        new=patch_upstream(raw,update_url)
        # Atomic replacement only after all validations. An upstream error never replaces last stable file.
        args.output.parent.mkdir(parents=True,exist_ok=True)
        tmp=args.output.with_name(args.output.name+'.tmp')
        tmp.write_text(new,encoding="utf-8")
        os.replace(tmp,args.output)
        report={
            "source_url":DEFAULT_SOURCE if args.fetch else "local-fixture",
            "source_sha256":digest(raw.encode('utf8')),
            "output_sha256":digest(new.encode('utf8')),
            "upstream_rules":len(rule_lines(raw)),
            "output_rules":len(rule_lines(new)),
            "automatic_self_update_url":update_url,
            "status":"PASS_STATIC_CHECKS_CLIENT_TEST_NOT_PERFORMED"
        }
        if args.metadata:
            args.metadata.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (PatchError,AssertionError,UnicodeError,OSError,ValueError) as e:
        print("FAIL_CLOSED: "+str(e),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
