---
title: EU CE for Consumer Electronics (EMC / LVD / RED / RoHS)
jurisdiction: EU
authority: European Commission
source: https://commission.europa.eu/single-market/european-standards/harmonised-standards_en
category: electronics
review_status: draft
---

# EU CE for Consumer Electronics (EMC / LVD / RED / RoHS)

> ⚠️ draft：内容按法规公共知识整理，正式使用前必须对照官方来源核验。

## 一台电子设备适用哪些指令
A consumer electronic device (action camera, gimbal, wireless remote) with Wi-Fi/Bluetooth is simultaneously covered by:
- **Radio Equipment Directive (RED) 2014/53/EU** — any equipment intentionally emitting/receiving radio waves. RED covers three essential requirements: safe use (health & safety incl. EMF), no harmful interference + good spectrum use, and EMC.
- **EMC Directive 2014/30/EU** — emissions and immunity (for radio equipment the EMC essential requirements are folded into RED; EMC Directive applies to non-radio electronics).
- **Low Voltage Directive (LVD) 2014/35/EU** — electrical safety for equipment 50–1000 V AC / 75–1500 V DC input. USB-charged 5 V devices are below the LVD voltage window but EN 62368-1 testing is still the market norm; mains chargers/adapters are squarely in LVD scope.
- **RoHS 2011/65/EU** — restricted substances in electrical & electronic equipment; affixing CE requires RoHS compliance as well.

An accessory that is purely mechanical (aluminum selfie stick without electronics, tempered-glass lens protector) is NOT covered by any of these and must not be CE marked on this basis.

## 常用协调标准
Conformity with harmonized standards (published in the Official Journal) gives presumption of conformity:
- **EN 62368-1** — audio/video, information and communication technology safety (replaced EN 60065 and EN 60950-1); applies to cameras, chargers, gimbals.
- **EN 55032 / EN 55035** — EMC of multimedia equipment (emission / immunity).
- **EN 300 328** — 2.4 GHz wideband transmission (Wi-Fi/BT); **EN 301 893** — 5 GHz; **EN 303 687** — 6 GHz.
- **EN 62479 / EN 62311** — human exposure to electromagnetic fields (EMF), needed for RED.

## 合格评定流程
1. Testing at a competent lab against the applicable harmonized standards.
2. RED allows **self-declaration** for most consumer radio equipment (no notified body required unless using non-harmonized standards or specific band conditions).
3. Draw up the **EU Declaration of Conformity (DoC)** listing every directive applied (RED, EMC as applicable, LVD if in voltage scope, RoHS) and the standards used; keep technical file 10 years.
4. Affix CE; for radio equipment also keep the **notification of radio-band usage** in the manual and include the maximum RF power.
5. Non-EU manufacturers need an EU-established responsible person (GPSR/MSR 2019/1020) — importers and marketplaces will demand this.

## 常见踩坑
- Marking CE on purely mechanical accessories "for safety" is a violation (CE only where legislation applies).
- Wi-Fi module cameras must be tested with the radio active in final housing — modular approvals of the chip do not transfer automatically.
- CE self-declaration is not a "certificate": marketplace listings that require a "CE certificate" are actually asking for the DoC + test reports.
