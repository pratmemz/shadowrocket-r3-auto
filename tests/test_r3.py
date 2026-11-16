import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_r3 import PatchError, patch_upstream, extract_section, rule_lines, domain_policy


class R3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'tests/fixtures/original_user.conf').read_text(encoding='utf8')
        cls.gold=(ROOT/'tests/fixtures/r3_user_verified.conf').read_text(encoding='utf8')

    def test_current_original_generates_equivalent_r3(self):
        got=patch_upstream(self.source,None)
        # Ignore only explanatory header and the disabled update-url comment.
        def core(s):
            s=s[s.index('[General]'):]
            lines=[]
            for line in s.splitlines():
                if line.startswith('#') and ('update-url' in line or 'R3 stable' in line):
                    continue
                if line.startswith('#') or not line.strip():
                    continue
                lines.append(line.strip())
            return lines
        self.assertEqual(core(self.gold),core(got))

    def test_self_update_points_to_user_not_upstream(self):
        out=patch_upstream(self.source,'https://raw.githubusercontent.com/user/repo/main/sr_cnip_r3_auto.conf')
        self.assertIn('update-url = https://raw.githubusercontent.com/user/repo/main/sr_cnip_r3_auto.conf',out)
        self.assertNotIn('update-url = https://johnshall.github.io/',out)

    def test_upstream_broken_fails_closed(self):
        self.assertRaises(PatchError,patch_upstream,self.source.replace('GEOIP,CN,DIRECT','GEOIP,CN,PROXY'),None)
        self.assertRaises(PatchError,patch_upstream,self.source.replace('dns-server = https://dns.alidns.com/dns-query','dns-server = https://wrong.example/dns-query'),None)

    def test_domain_policies(self):
        out=patch_upstream(self.source,None)
        for name,expected in [('google.com','PROXY'),('www.youtube.com','PROXY'),('www.baidu.com','DIRECT'),('jd.com','DIRECT'),('xxx.cn','DIRECT')]:
            self.assertEqual(domain_policy(out,name),expected)

    def test_imported_rule_preservation(self):
        out=patch_upstream(self.source,None)
        self.assertIn('DOMAIN-SUFFIX,telegram.org,PROXY',out)
        self.assertIn('IP-CIDR,91.108.56.0/22,PROXY,no-resolve',out)
        self.assertEqual(out.count('[General]'),1)
        self.assertEqual(out.count('[Rule]'),1)


if __name__=='__main__': unittest.main()
