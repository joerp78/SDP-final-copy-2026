import time
from pico_lte.utils.status import Status
from pico_lte.core import PicoLTE
from pico_lte.common import debug

pico = PicoLTE()

pico.network.register_network()
pico.http.set_context_id()
pico.network.get_pdp_ready()

pico.http.set_server_url("http://sdp.joepaola.com/api/test")

debug.info("Sending GET")
result = pico.http.get()
debug.info(result)

time.sleep(5)
result = pico.http.read_response()
debug.info(result)
if result["status"] == Status.SUCCESS:
    debug.info("Get request succeeded.")