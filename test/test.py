from helios.field import *
from helios.spec import Spec

MODULE_TYPE = {
    0x00: "Unknown",
    0x03: "SFP/SFP+/SFP28",
    0x06: "XFP",
    0x0C: "QSFP",
    0x0D: "QSFP+",
    0x11: "QSFP28",
    0x18: "QSFP-DD (CMIS)",
    0x19: "OSFP (CMIS)",
    0x1E: "QSFP+ or later with CMIS",
    0x1F: "SFP-DD (CMIS)",
}
CMIS_IDS = {0x18, 0x19, 0x1E, 0x1F}
 
MODULE_STATE = {
    1: "ModuleLowPwr",
    2: "ModulePwrUp",
    3: "ModuleReady",
    4: "ModulePwrDn",
    5: "Fault",
}
 
MEDIA_TECH_OPTICAL = {
    0x01: "850 nm VCSEL",
    0x02: "1310 nm VCSEL",
    0x03: "1550 nm VCSEL",
    0x04: "1310 nm FP",
    0x05: "1310 nm DFB",
}
MEDIA_TECH_COPPER = {
    0x01: "Copper cable, unequalized",
    0x02: "Copper cable, passive equalized",
    0x03: "Copper cable, near + far end limiting active",
    0x04: "Copper cable, far end limiting active",
}
 
MEDIA_TYPE = {
    0x00: "Undefined",
    0x01: "Optical Interfaces: MMF",
    0x02: "Optical Interfaces: SMF",
    0x03: "Passive Copper Cables",
    0x04: "Active Cables",
    0x05: "BASE-T",
}
 
 
class CmisLowerPage(Spec):
    identifier    = U8(0, enum=MODULE_TYPE,                  doc="SFF-8024 id")
    rev_major     = Bits(1, 7, 4,                            doc="CMIS major rev")
    rev_minor     = Bits(1, 3, 0,                            doc="CMIS minor rev")
    module_state  = Bits(3, 3, 1, enum=MODULE_STATE)
    interrupt_n   = Bit (3, 0,                               doc="Interrupt asserted")
    media_type    = U8(85, enum=MEDIA_TYPE,                  doc="Media type code")
 
    revision      = Computed(lambda c: f"{c.rev_major}.{c.rev_minor}",
                             doc="CMIS rev as MAJOR.MINOR")
    is_cmis       = Computed(lambda c: c.raw_int("identifier") in CMIS_IDS,
                             doc="True if module advertises CMIS")
    is_copper     = Computed(lambda c: c.media_type == "Passive Copper Cables")
 
    temperature   = I16(14, scale=1/256.0, unit="C",
                        when=lambda c: c.module_state == "ModuleReady")
    vcc_supply    = U16(16, scale=1e-4,    unit="V",
                        when=lambda c: c.module_state == "ModuleReady")
 
    media_tech    = U8(212,
                       enum=lambda c: MEDIA_TECH_COPPER if c.is_copper
                                      else MEDIA_TECH_OPTICAL,
                       doc="Interpretation depends on media_type (byte 85)")
 
 
class CmisPage00(Spec):
    identifier  = U8   (128, enum=MODULE_TYPE)
    vendor_name = Ascii(129, 16)
    vendor_oui  = Hex  (145,  3,                             doc="IEEE OUI")
    vendor_pn   = Ascii(148, 16)
    vendor_rev  = Ascii(164,  2)
    vendor_sn   = Ascii(166, 16)
    date_code   = Ascii(182,  8,                             doc="YYMMDDLL")
 
 
def _build_demo_dump(state: int = 3, media: int = 0x02) -> bytes:
    d = bytearray(256)
    d[0]  = 0x18                                       # QSFP-DD CMIS
    d[1]  = 0x52                                       # CMIS rev 5.2
    d[3]  = (state << 1) | 0                           # module state
    d[14:16] = (int(25.5 * 256)).to_bytes(2, "big", signed=True)
    d[16:18] = (33000).to_bytes(2, "big")
    d[85] = media                                      # media type
    d[212] = 0x03                                      # media tech code
    d[128] = 0x18
    d[129:145] = b"ACME OPTICS".ljust(16, b" ")
    d[145:148] = bytes.fromhex("AABBCC")
    d[148:164] = b"QDD-400G-DR4-S".ljust(16, b" ")
    d[164:166] = b"01"
    d[166:182] = b"SN1234567".ljust(16, b" ")
    d[182:190] = b"240315AB"
    return bytes(d)
 
 
if __name__ == "__main__":
    print("=" * 72)
    print("Module READY, optical SMF media (byte 212 -> optical enum)")
    print("=" * 72)
    print(CmisLowerPage.parse(_build_demo_dump(state=3, media=0x02)))
 
    print()
    print("=" * 72)
    print("Module READY, passive copper media (byte 212 -> copper enum)")
    print("=" * 72)
    print(CmisLowerPage.parse(_build_demo_dump(state=3, media=0x03)))
 
    print()
    print("=" * 72)
    print("Module still powering up -> monitor fields skipped")
    print("=" * 72)
    print(CmisLowerPage.parse(_build_demo_dump(state=2, media=0x02)))
 
    print()
    print(CmisPage00.parse(_build_demo_dump()))
