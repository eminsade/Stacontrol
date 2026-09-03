"""ETABS Bridge - uzak ajan uzerinden ETABS COM API'sine erisim.

Bu paket uc parcadan olusur:

* ``etabs_bridge.server``  : Ajan ile web uygulamasini bulusturan is kuyrugu (FastAPI).
* ``etabs_bridge.client``  : Streamlit sayfalarinin kullandigi, COM arayuzunu birebir
                             taklit eden ``RemoteSapModel`` proxy'si.
* ``etabs_bridge.agent``   : Kullanicinin bilgisayarinda calisan, ETABS'e COM ile
                             baglanip tablo okuyan kucuk istemci.
"""

__version__ = "1.0.0"
