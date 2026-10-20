---
title: US FCC Equipment Authorization (RF Devices)
jurisdiction: US
authority: FCC (Federal Communications Commission)
source: https://www.fcc.gov/oet/ea/rf-device
category: electronics
review_status: draft
---

# US FCC Equipment Authorization (RF Devices)

> ⚠️ draft：内容按法规公共知识整理，正式使用前必须对照 FCC 官网核验。

## 适用范围
Any device that intentionally or unintentionally emits radio-frequency energy and is sold or used in the US falls under FCC rules (47 CFR). Part 15 covers most consumer electronics: intentional radiators (Wi-Fi/Bluetooth modules, remote controls) and unintentional radiators (digital circuitry in almost every electronic product — LED strips, chargers, smart home devices).

## 授权途径
Part 15 device classes and their authorization procedures:
- **Verification** (unintentional radiators, e.g. TV receivers): manufacturer self-tests, keeps records; no filing.
- **Declaration of Conformity (DoC)** (e.g. personal computers, PC peripherals): testing per procedure, no FCC filing required, DoC paperwork must be kept.
- **Certification** (intentional radiators — most wireless products): application must be filed by a **Telecommunication Certification Body (TCB)** with test data from an accredited lab; the device gets an **FCC ID**.
Devices with a single modular transmitter (e.g. a pre-certified Wi-Fi/BT module with its own FCC ID and modular approval) can integrate the module and reference its grant, subject to the module's integration instructions.

## 测试与标签
1. Testing must follow FCC measurement procedures (e.g. ANSI C63.4 for unintentional radiators) at an accredited lab.
2. Certified devices must bear the **FCC ID** (on the product label, format: GranteeCode-ProductCode) and comply with user-manual notification statements.
3. Devices subject to DoC/verification must meet label requirements including the FCC logo where applicable.
4. Digital circuitry at 108–500 MHz etc. has specific emission limits under § 15.107/15.109; battery-powered DC devices may be exempt from unintentional-radiator testing under § 15.103.

## 跨境卖家注意事项
- The **importer** is responsible: imports of non-compliant RF devices are subject to detention (Customs works with the FCC).
- Marketing/selling a wireless product without required certification can trigger FCC Enforcement Bureau action (forfeitures per violation per day).
- Amazon and other marketplaces increasingly require FCC ID documentation for wireless-capable listings.
