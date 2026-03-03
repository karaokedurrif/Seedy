# Implementation of an IoT‑Based Livestock Monitoring System Using Mioty Technology (clean text)

_Extracted from the PDF into clean text for easier indexing/RAG in Open WebUI._

Internet Technology Letters

LETTER

OPEN ACCESS

Implementation of an IoT-Based Livestock Monitoring
System Using Mioty Technology
Luis Rubio Fuentes

| Andoni Beriain Rodríguez | Yuemin Ding

Department of Electronics, Tecnun, University of Navarra, Pamplona, Spain
Correspondence: Luis Rubio Fuentes (lrubiofuent@alumni.unav.es)
Received: 21 March 2025 | Revised: 29 July 2025 | Accepted: 3 September 2025
Keywords: automation | IoT | livestock | LoRa | LPWAN | Mioty | smart farming

ABSTRACT
Environmental monitoring and control in pig farms is fundamental not only for the farmer’s economy, but also for animal welfare.
The detection and control of basic parameters such as temperature, humidity, and luminosity are crucial for the development,
rearing, and weaning of pigs. This paper presents the implementation of a monitoring system using M3B Magnolinq devices,
based on Mioty, which is an emerging technology for Low-Power Wide-Area Network (LPWAN). The system was deployed on
a farm in Extremadura (Spain) during the summer, demonstrating the high functionality and productivity for pig farming. The
system provides real-time temperature, humidity, and luminosity data, easily accessible to farmers from any device.

1 |

Introduction

The livestock industry faces numerous challenges related to
economic viability, environmental sustainability, and technological innovation. The global average temperature continues
to rise, which is why farmers’ heat management is critical to
ensure farm productivity. Heat stress negatively affects the health
and productivity of pigs, especially pregnant and lactating sows
[1]. Studies have estimated annual losses of USD 299 million
in the US swine industry due to environmental factors such
as temperature and humidity [2]. Furthermore, fewer farms
with more animals intensify biosanitary risks [3] (e.g., prenatal
heat stress [4]), while energy costs for climate control continue
to rise.
Duroc and Iberian Duroc pigs that experience different temperature variations during their growth, fattening, and finishing
stages show variable behavior in their growth curve, weight gain,
efficiency, and meat yield. Pigs in a 23˚C environment show a
higher growth pattern, higher feed consumption resulting in
higher fattening and, therefore, higher carcass yield [5]. Light
also plays a role in pig growth, with varying light gradients

affecting behavior and health, including issues like tear staining,
conjunctivitis, and tail lesions [6].
Many devices [7] have been proposed for the measurement of
temperature, humidity, and luminosity in pig farms; these devices
are mostly placed independently in the control centers of each
thermal control device in the farms:
• The EXAFAN system measures temperature and humidity
with probes at room entrances; WiFi functionality entails
extra costs but remains widely used due to its long-standing
reputation [8].
• To have data in real time and without the extra economic
outlay, a Raspberry Pi 4 model B device with sensors can be
used [9], as shown in Table 1. It is portable, scalable, and
affordable, but its implementation is more complex and less
intuitive for farmers, relying on LTE technology, which is
affected by signal coverage and subscription costs in the agricultural area studied [10, 11].
• A study from Korea measured temperature, humidity, and
volatile organic compounds (VOCs) every 10 min. The

---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------This is an open access article under the terms of the Creative Commons Attribution-NonCommercial-NoDerivs License, which permits use and distribution in any
medium, provided the original work is properly cited, the use is non-commercial and no modifications or adaptations are made.
© 2025 The Author(s). Internet Technology Letters published by John Wiley & Sons Ltd.
Internet Technology Letters, 2025; 8:e70141
https://doi.org/10.1002/itl2.70141

Comparison of continuous monitoring devices.

Location

Device

Real-time

Accuracya

Power source

Life battery

Protocol

Access

Outside [8]

EXAFAN CSP

Yes

High

Power plug

Unlimited

WiFi (Extra)

ExaRed (Extra)

Near mother [9]

Raspberry Pi 4B

Yes

Moderate

Power plug

N/A

LTE

Web-based GUI

Near mother [10]

RAK3172

Yes

Moderate

2 × AA

1 year

LoRa

Node-red

Augan sensor

Yes

Moderate

N/A

N/A

SigFox

Augan APP

Yes

Moderateb

CR2032

N/A

Mioty

Things Board

Outside [11]
Near mother

M3B Magnolinq

a How well the measurement reflects temperature and humidity data.
b Comparative with the first system for each hour in the farm.

monitoring revealed changes in pig behavior, including feed
intake, standing, lying time, and drinking frequency, in
response to temperature adjustments ranging from 18˚C to
30˚C [12].

the farmer’s productivity and profitability. IoT technology, being
part of the digital economy of the future, offers the company a
reduction in operating costs, an increase in animal welfare certifications, and an increase in production efficiency [16].

In summary, previous studies demonstrate that temperature and
relative humidity significantly impact the daily feeding behavior
of pigs [13]. While several methods have been proposed and compared in this paper for Smart farms (Table 1), their implementation remains challenging in primary sector operations despite
their accuracy and reliability.

The study evaluates two key growth phases: pre-weaning (first
28 days) and the transition phase (next 35 days). In a batch of
2354 pigs at the start with an average weight of 7.80 kg/pig,
2319 remained after 35 days with an average weight gain of
0.375 kg/day achieving a processing index of 1.5123 kg feed/kg
meat. The total output was 48,525.075 kg, generating an estimated revenue between €124,709.44 and €129,561.95, based on
the market price from September 2024 (2.56–2.66 ± 0.01 €/Kg).

Recent advances in smart farming and precision agriculture have
demonstrated how IoT-based solutions can revolutionize the primary sector. From goat farming initiatives focused on improving meat quality through real-time health monitoring with load
cells and thermal sensors [14] to broader smart environment and
forest city frameworks aimed at balancing environmental protection, resource efficiency, and community engagement [15], these
efforts showcase the transformative potential of integrating IoT
into agricultural and environmental systems.
In this work, we have reinforced the novelty by demonstrating, to our knowledge, the first practical application of Mioty
LPWAN technology in agriculture and livestock farming. This
goes beyond merely monitoring temperature and humidity,
showcasing Mioty’s robustness and scalability to improve animal
welfare, productivity, and operational efficiency.
The paper is structured in the following way: Section 2 introduces the proposed system and provides an initial notion of its
potential economics. Section 3 details the IoT architecture and
comparative design considerations. Section 4 shows implementation shown in Section 5, with some results. Finally, Section 6
shows conclusions.

2 | Economic Potential of IOT for Swine
Farming
In this section we discuss some observations of the positive
impact on a farm and some possible future implementations.

2.1 |

Economical Benefit for Swine Farmers

The implementation of monitoring systems on pig farms, such
as those described in this paper, has a significant impact on

A simulation is performed based on the effects of environmental
conditions on pig growth [17]. Precise control of temperature and
humidity reduces heat stress, which results in an increase in the
average daily gain of pigs by 5% to 10%. With the proposed system, an improvement of up to 0.413 kg/day could raise the total
weight to 51,609 kg, generating revenues between €132,636.01
and €137,796.95 for 2319 pigs (6.36% profit). This result offers
a promising indication of how environmental monitoring could
positively impact farm profitability [18].

2.2 | Further Implementation
Air conditioning systems in pig farming have evolved over time to
maximize performance, with commercial solutions such as those
from EXAFAN representing significant advances. Various methods of climate control with hydration via PLCs have been extensively studied, especially in Asia [19, 20]. However, most current
systems do not use IoT communication protocols, meaning that
the architecture discussed in this paper can serve as a basic integration layer combining the advantages of Mioty technology with
existing control infrastructures.
Moreover, the Mioty M3B Magnolinq Makerboard sensors support communication with a central Gateway capable of managing
numerous nodes on a farm [21], which ensures scalability for
larger operations. The STM32L072 SoC on board includes multiple ADC channels, facilitating the addition of extra sensors. This
modularity means the system can be readily extended beyond
environmental monitoring to include indirect health indicators, ultimately supporting more comprehensive pig growth and
welfare management. Future enhancements could also involve
acoustic modules, such as MAX9814, where music lowered cortisol and increased levels of IgG, IL-2, and IFN-y [22].
Internet Technology Letters, 2025

TABLE 1 |

IOT System Proposal

The main objective of this work is to implement a real-time
environmental monitoring system for pig farms that is efficient,
robust, non-invasive, and has a positive impact on farm economics. This is achieved by using (i) a Mioty Gateway and (ii)
Mangolinq M3B Makerboards.
The system’s architecture includes:
1. Mioty Gateway (WEPTECH AVA): Collects data from the
sensor nodes, decrypts and forwards it securely to the IoT
server [23], while managing synchronization and network
efficiency.
2. Platform and Data Management: Processes and visualizes
data on a dashboard, enabling real-time monitoring and historical analysis.
Figure 1 illustrates how the mioty system works. The pig breeding process, consisting of mating, farrowing, and weaning, can be
effectively monitored, optimizing environmental conditions and
improving economic returns per pig reared [24].
The monitoring system must provide high accuracy, minimal
invasiveness, and long-term durability, while ensuring compatibility and scalability.

3.1 | Comparative Context and Design
Considerations
Mioty technology can offer several improvements over LoRa,
as demon- strated by the comparative study from Fraunhofer
[23]. Various IoT-based monitoring solutions have been proposed
in the agri-food sector, focusing primarily on crops, aquaponics
or small ruminants. Table 2 summarizes representative systems
from the literature, emphasizing their typical reliance on WiFi or
GSM connectivity, which limits scalability and rural applicability.
Unlike these systems, our solution is designed specifically for
intensive swine farming, leveraging Mioty LPWAN technology
(ETSI TS 103357), which ensures long-range, low-power operation with high robustness against interference. Recent comparative studies demonstrate that Mioty can sustain up to 44 000
packets/min/MHz at 10% PER, surpassing LoRa SF12 by more
than 1000× under similar robustness [30], while also achieving

TABLE 2
livestock.

| Comparison of related IoT applications in agriculture and

References

Domain

Connectivity/scale

[25]

Crop irrigation

WiFi (small, on-site)

[26]

Hydroponics

WiFi/MQTT (small indoor)

[27]

Aquaculture

GSM (medium lakes)

[15]

Smart city env.

Various (city-wide)

[14]

Goat farming

WiFi (local, power-limited)

[28]

AI Hydroponics

WiFi/cloud (experimental)

[29]

Aquaponics

WiFi/MQTT (moderate scale)

This work

Swine farming Mioty LPWAN (rural, scalable)

a three-fold improvement in battery life [31]. These advantages
position it as an optimal candidate for scalable rural deployments
where conventional WiFi or GSM solutions do not meet coverage or capacity requirements. Mioty achieves a network capacity of over 1.5 million telegrams per day per base station under
real-world conditions, vastly outperforming LoRaWAN or Sigfox, which typically support only a few thousand transmissions
per day in dense deployments. Also, the TSMA telegram splitting
protocol makes Mioty inherently robust to interference. In field
trials, Mioty maintained full packet integrity under strong WiFi
and LoRaWAN interference, whereas LoRa suffered packet loss
rates exceeding 20% [30].
From the perspective of data transmission reliability, security,
and privacy, MIOTY offers outstanding capabilities in the communication between sensor nodes and the gateway. Its advanced
Forward Error Correction (FEC) method enables full reconstruction of messages using only half of the transmitted radio
bursts. Additionally, MIOTY includes integrated security features such as AES-128 encryption and a 32-bit cipher-based
Message Authentication Code (CMAC) for authentication and
integrity verification. Replay protection is ensured via a 24-bit
packet counter, and an optional variable MAC mode enables
user-defined authentication functions. Regarding upper-layer
connections (from the gateway to the server) data security
depends on the system architecture: on-premise, private cloud,
or public cloud deployments each require standard encryption
protocols, similar to other IoT applications.

4 |

System Implementation

This section introduces the system design with a focus on on-farm
implementation using Mioty. The system is equipped with sensors to ensure optimal biosanitary conditions. The system’s SoC,
the STM32L072RBT, receives the temperature, humidity and
brightness data. Brightness detection also affects pig activity
cycles and behavior [12].

4.1 |

FIGURE 1

|

Architecture diagram for the Mioty System.

Functional Tasks of the Architecture

The functional tasks of the architecture are made possible by the
system’s internal operation, which follows the sequence depicted
in the block diagram shown in Figure 2.

3 |

FIGURE 2

|

| Thingsboard dashboard.

Block diagram of M3B Magnolinq.

After installation, each sensor is registered on the web platform
for data reception, and the dashboard is developed using ThingsBoard for monitoring Figure 5.

5 |

FIGURE 3

|

System components and 3D printed case.

Experimental Results

The M3B Magnolinq sensor system was installed in a Duroc ×
Iberian pig farm in August 2024 to monitor 12 sows and 84 offspring in a farrowing and weaning room. The experiment aimed
to compare the growth of pigs in two adjoining rooms, one with
Mioty environmental monitoring and the other without, to assess
the system’s economic impact.

5.1 | System Deployment
The sensor system (represented by the red dot in Figure 6) was
placed in the center of the room, about 2 m from the floor, based
on previous studies in pig farms [33], ensuring optimal monitoring. The room has two windows with ventilation systems on the
sides, as it is shown in Figure 6.
The system was deployed on a farm with 96 pigs, which remain
confined in the spaces shown in Figure 6. The Mioty Gateway was
placed in an indoor office for protection. Due to incompatibilities with MQTT, data transmission to the IoT platform required a
Python script using the Paho client [32].
FIGURE 4

4.2 |

|

Gateway (cross) and Magnolinq sensors.

System Implementation

The system consists of four components as shown in Figure 3: an
AVA Gateway, a USB C Raspberry PI power supply, a LAN cable
with DHCP support, a USB 2.0 to Serial TTL Converter, five M3B
Magnolinq sensors with SMA antennas, and a computer placed
in the farm, Figure 4.
The system sensors are programmed using the ARDUINO IDE
programming environment, connected via the USB 2.0 to Serial
TTL Converter. It requires the addition of several libraries recommended by the sensor configuration guide [32]. M3B Magnolinq
sensors are installed in show rooms, protected by a 3D-printed
case (Figure 3).

Although this integration used a Python Paho client in order to
gain implementation flexibility, this would not be necessary in
established applications. Commercially available MIOTY gateways, such as the WisGate Connect series from RAK wireless,
support native integration with major IoT platforms through
MQTT or HTTPS protocols. The rest of the function of the IoT
service can be deployed either on an on-premise server, as done
in this project with Python, or using private or public cloud
infrastructure. Therefore, full end-to-end integration is achievable without additional software bridges.
Figure 7 shows the location and arrangement of the sensor in the
farm. The sensor is tethered to a main beam on which the lighting and power systems are arranged. The use of tie-down flanges
allows for easy installation and no modification to the infrastructure for the convenience of the farmer.
Internet Technology Letters, 2025

FIGURE 5

| Temperature graphic Magnolinq versus Exafan RVC.

temperature and ±1.5% RH for humidity, detecting sensitive
environmental changes. The system also maintained stable
real-time data transmission with low latency, thanks to Mioty
technology, and no packet loss was observed even at 100 m from
the AVA Gateway.
|

Farrowing (up) and weaning (down) rooms for pigs.

FIGURE 7 |

Location and placement of M3B Magnolinq sensor.

FIGURE 6

5.2 |

Validation of Readings

The reliability of Mioty sensor readings was assessed by comparing them with EXAFAN RVC measurements in farrowing rooms
during a summer morning (see Figure 7). Since the EXAFAN
RVC lacks data logging, environmental parameters were manually recorded every 30 min.
Both systems show similar temperature trends 8, confirming
Mioty’s accuracy. Minor deviations, such as 26.7999˚C versus
25.5˚C at 9:04, do not compromise consistency. Mioty also stabilizes quickly after temperature changes and operates wirelessly,
unlike EXAFAN. While EXAFAN maintains stable humidity near
52%, Mioty shows some fluctuation due to battery drain, yet
remains an effective monitoring option (Figure 8).

5.3 |

Device Performance

The accuracy of the M3B Magnolinq sensors was exceptional.
The SHT31A sensors showed minimal deviations of ±0.2˚C for

Studies show that pigs in temperature-controlled environments
(t24-24-21 conditions) achieve higher growth rates and feed efficiency [5], demonstrating Mioty’s potential to optimize livestock farm performance. It also enhanced energy management by optimizing ventilation and heating based on real-time
data, reducing energy consumption and operating costs while
improving productivity, positively impacting farm profitability.
Comparative analysis with conventional systems like EXAFAN
showed equivalent accuracy, with the Mioty system demonstrating superior real-time variation capture, which benefits livestock management decisions. While actual battery life was not
measured in this deployment, the M3B Magnolinq sensor is
expected to exceed 12 months of autonomy based on Mioty’s
low-power transmission benchmarks and the device’s internal
configuration [30].
The efficiency of Mioty also results in significantly lower energy
usage: in comparative tests with 8-byte payloads at one message per hour, Mioty consumed only 45% of the energy required
by LoRaWAN Class A [30]. This makes it a suitable candidate for scalable rural deployments with minimal maintenance
requirements.

6 |

Conclusions

While IoT and AI-based systems have demonstrated significant
benefits in smart crop management [25, 26, 28], aquaculture
monitoring [27, 29], urban-scale sustainability [15], and even in
livestock such as goats to improve meat quality [14], the use of
Mioty technology in intensive pig farming remains largely unexplored. In this work, we implemented a Mioty-based system to
collect real-time temperature, humidity, and light data at “Finca
Mirabel” (S.L Mirabel) in Extremadura, using an M3B Magnolinq
sensor, an AVA Weptech gateway, and a ThingsBoard platform.
Although still at the prototype stage and monitoring only basic
parameters, the setup enabled a preliminary economic evaluation. Our results suggest potential improvements in technological
modernization, operational costs, animal welfare, and rural sustainability. This study represents an initial step toward broader
Mioty applications in smart farming.

FIGURE 8

Acknowledgments
The authors thanks the reviewers for their valuable comments. This work
was supported by the University of Navarra.

15. W. Listianingsih and T. Susanto, “Toward Smart Environment and
Forest City Success: Embracing Sustainable Urban Solutions,” Indonesia
Journal on Computing (Indo-JC) 8, no. 2 (2023): 23–34.

Conflicts of Interest

16. S. Neethirajan, “AI in Sustainable Pig Farming: Iot Insights Into Stress
and Gait,” Agriculture 13, no. 8 (2023): 1706.

The authors declare no conflicts of interest.
Data Availability Statement
The data that support the findings of this study are available on request
from the corresponding author. The data are not publicly available due to
privacy or ethical restrictions.
Peer Review
The peer review history for this article is available at https://www.
webofscience.com/api/gateway/wos/peer-review/10.1002/itl2.70141.
References

17. A. da Fonseca, K. de Oliveira, C. Vanelli, S. W. Sotomaior, and L. Costa,
“Impacts on Performance of Growing-Finishing Pigs Under Heat Stress
Conditions: A Meta-Analysis,” Veterinary Research Communications 43
(2018): 12–43.
18. R. O. Myer and R. A. Bucklin, Influence of Hot-Humid Environment on
Growth Performance and Reproduction of Swine 1 (N/A, Tech. Rep, 2001),
https://api.semanticscholar.org/CorpusID:130979087.
19. Z. Shi, X. Li, T. Wang, et al., “Application Effects of Three Ventilation Methods on Swine in Winter,” Agronomy Journal 114, no. 11 (2021):
1915–1922.
20. L. Yang, H. Wang, R. Chen, D. Xiao, and B. Xiong, “Research Progress
and Prospect of Intelligent Pig Factory,” Journal of South China Agricultural University 44, no. 1 (2023): 13.

1. J. Johnson, L. Brito, C. Maltecca, and F. Tiezzi, “400 Improving Heat
Stress Resilience to Reduce the Negative Effects of Pre- and Postnatal Heat
Stress in Swine,” Journal of Animal Science 100, no. 9 (2022): 47–48.

21. Weptech.de, “Weptech Elektronik GMBH,” (2024), https://www.
weptech.de/en/solutions/mioty-solutions.html.

2. B. Cobanov and G. Schnitkey, “Economic Losses From Heat Stress by
Us Livestock industries1,” Journal of Dairy Science 86, no. 6 (2003): 52–53.

22. J. Li, X. Li, H. Liu, et al., “Effects of Music Stimulus on Behavior
Response, Cortisol Level, and Horizontal Immunity of Growing Pigs,”
Journal of Animal Science 99, no. 5 (2021): 5–9.

3. P. y. A. Ministerio de Agricultura, “Producción y mercados
ganaderos: Indicadores económicos del sector porcino,” 2024 Ministerio de Agricultura, Pesca y Alimentación, Tech. Rep, https://www.
mapa.gob.es/es/ganaderia/temas/produccion-y-mercados-ganaderos/
sectores-ganaderos/porcino/indicadoreseconomicos.aspx.
4. J. Johnson, “269 Bioenergetic Consequences of Pre- and Post-Natal
Heat Stress on Swine Productivity,” Journal of Animal Science 101, no.
10 (2023): 59.
5. W. M. Rauw, E. de Mercado, L. G. Raya, L. A. G. Cortes, J. J. Ciruelos,
and E. Gómez-Izquierd, “Impact of Environmental Temperature on Production Traits in Pigs,” Scientific Reports 10 (2020): 1–12.
6. A. Scaillierez, S. van Nieuwamerongen, I. Boumans, P. Tol, S. Schnabel,
and E. Bokkers, “Effect of Light Intensity on Behaviour, Health and
Growth of Growing-Finishing Pigs,” Animal 18, no. 2 (2024): 101092.
7. S. Mahfuz, H.-S. Mun, M. Dilawar, and C.-J. Yang, “Applications of
Smart Technology as a Sustainable Strategy in Modern Swine Farming,”
Sustainability 14 (2022): 2607.
8. EXAFAN, “Controlador CSP,” (2024), https://exafan.com/controlad
or-csp.
9. E. Arulmozhi, A. Bhujel, N. Deb, et al., “Development and Validation
of Low-Cost Indoor Air Quality Monitoring System for Swine Buildings,”
Sensors 24, no. 5 (2024): 1–17.
10. L. R. Fuentes, “Diseño hardware-software de un dispositivo para monitorización con transmisión de datos por lora,” (master’s thesis, Universidad Francisco de Vitoria, 2023).
11. AUGAN, “Augan tecnología en ganadería,” (2024), https://augan.es/
control-de-temperatura-humedad.
12. Y. Kim, M. Song, S. Lee, et al., “Evaluation of Pig Behavior Changes
Related to Temperature, Relative Humidity, Volatile Organic Compounds, and Illuminance,” Journal of Animal Science and Technology 63,
no. 7 (2021): 790–798.
13. Z. Peppmeier and M. Knauer, “181 Effect of Temperature and Humidity on Daily Feeding Behavior in Swine,” Journal of Animal Science 101
(2023): 8–9.

23. Fraunhofer-Gesellschaft, Miotytm – Physical Layer Technology
(Fraunhofer IIS, Tech. Rep, 2018).
24. R. Cisneros, R. González Avalos, C.-A. Citlalli, and R.-Q. Leonardo,
“El análisis de correlación xy en la alimentación de cerdos y su efecto en
la ganancia de masa muscular,” 1, no. 9 (2021): 31.
25. S. Hossain and M. P. H. B. Chowdhury, “Agrosense: An IoT-Based
Manual Crops Selection Farming,” International Journal on Information
and Communication Technology (IJoICT) 10, no. 1 (2024): 53–61.
26. S. Suhesti, A. G. Putrada, and R. R. Pahlevi, “The Effectiveness of
Automated Sonic Bloom Method in an Iot-Based Hydroponic System,”
International Journal on Information and Communication Technology
(IJoICT) 7, no. 2 (2021): 58–70.
27. N. A. Suwastika, S. Prabowo, and B. Erfianto, “Upwelling Solution
Prototype Using Wireless Sensor Network,” International Journal on
Information and Communication Technology (IJoICT) 2, no. 2 (2016): 37.
28. S. D. Putra, H. Heriansyah, E. F. Cahyadi, K. Anggriani, and M. H. I. S.
Jaya, “Development of Smart Hydroponics System Using Ai-Based Sensing,” Jurnal Infotel 16, no. 3 (2024): 474–485.
29. R. Ratnasih, D. Perdana, and Y. G. Bisono, “Performance Analysis
and Automatic Prototype Aquaponic of System Design Based on Internet of Things (Iot) Using Mqtt Protocol,” Jurnal Infotel 10, no. 3 (2018):
130–137.
30. J. Robert and T. Lauterbach, Mioty Comparative Study Report (Technische Universität Ilmenau, Tech. Rep, 2024).
31. O. Zerai, M. Striegel, and T. Krone, Lorawan and Mioty: A Study on
Packet Reception and Energy Consumption in the Industrial Internet of
Things (IFM Electronic GmbH, Tech. Rep, 2023), 6.
32. LZE, “Mioty Developer Page,” (2024), https://developers.miotyalliance.com/mioty-m3b-makerboard/.
33. U.-H. Yeo, S.-Y. Lee, P. Sejun, et al., “Determination of the Optimal
Location and the Number of Sensors for Efficient Heating, Ventilation,
and Air Conditioning System Operation in a Mechanically Ventilated Pig
House,” Biosystems Engineering 229, no. 5 (2023): 1–17.

Internet Technology Letters, 2025

14. J. Jumi, “Design and Building of a Breeding House for Iot-Based Goat
Farming,” Jurnal Infotel 16, no. 3 (2024): 581–597.