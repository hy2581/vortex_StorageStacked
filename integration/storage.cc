#include "storage.hh"
#include "aou_backend.hh"
#include "systemc/tlm_bridge/gem5_to_tlm.hh"
#include "systemc/utils/tracefile.hh"
#include "sim/core.hh"
#include <stdexcept>
#include "link_config.h"

namespace storage_axi {
using namespace sc_core;
Bridge::Bridge(const gem5::StorageBridgeParams& p)
    : Bridge(sc_module_name(p.name.c_str()), p) {}
Bridge::Bridge(sc_module_name n, const gem5::StorageBridgeParams& p)
    : sc_module(n),
      clock("aclk", sc_time::from_value(p.period)),
      master("master", p.outstanding, p.stalls, p.trace_dir),
      wrapper(master.socket, std::string(name()) + ".tlm", gem5::InvalidPortID),
      monitor("monitor", wires, p.trace_dir), directory(p.trace_dir) {
    monitor.clk(clock); monitor.resetn(resetn);
    master.clk(clock); master.resetn(resetn); master.axi.bind(wires);
    if (p.outstanding > 1023) throw std::runtime_error("AoU supports at most 1023 live IDs");
    master.maxId = 1023;
    StorageConfig storage;
    storage.base = p.base; storage.size = p.size;
    storage.planes = p.planes; storage.replay = p.replay;
    storage.memsim_slots = p.memsim_slots; storage.memsim_channels = p.memsim_channels;
    storage.memsim_scale = p.memsim_scale; storage.memsim_queue = p.memsim_queue;
    storage.memsim_response_hold = p.memsim_response_hold;
    storage.memsim_standard = p.memsim_standard; storage.trace_dir = p.trace_dir;
    aou = std::make_unique<AouBackend>("aou", storage);
    aou->clk(clock); aou->resetn(resetn); aou->axi.bind(wires);
    master.functional = [](tlm::tlm_generic_payload& gp) {
        gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
        return 0u;
    };
    static bool conversionInstalled = false;
    if (!conversionInstalled) {
        sc_gem5::addPacketToPayloadConversionStep([](gem5::PacketPtr pkt, tlm::tlm_generic_payload& gp) {
            auto* a = gp.get_extension<RequestAttributes>();
            if (!a) { a = new RequestAttributes(); gp.set_auto_extension(a); }
            const auto& be = pkt->req->getByteEnable();
            a->enables.assign(pkt->getSize(), 0xff);
            if (!be.empty()) {
                sc_assert(be.size() == pkt->getSize());
                for (unsigned i = 0; i < be.size(); ++i) a->enables[i] = be[i] ? 0xff : 0;
            }
            gp.set_byte_enable_ptr(a->enables.data());
            gp.set_byte_enable_length(a->enables.size());
            a->requestor = pkt->req->requestorId();
            a->hasStream = pkt->req->hasStreamId();
            a->stream = a->hasStream ? pkt->req->streamId() : 0;
            a->hasSubstream = pkt->req->hasSubstreamId();
            a->substream = a->hasSubstream ? pkt->req->substreamId() : 0;
            a->payloadDelay = pkt->payloadDelay;
            if (pkt->isAtomicOp() || pkt->isLLSC() || pkt->isLockedRMW() ||
                pkt->req->isSwap() || pkt->req->isCacheMaintenance())
                gp.set_command(tlm::TLM_IGNORE_COMMAND);
        });
        conversionInstalled = true;
    }
    std::ofstream link(directory + "/ucie_config.json");
    link << "{\"lanes\":" << LINK_LANES << ",\"rate_gtps\":" << LINK_RATE_GTPS
         << ",\"bits_per_symbol\":" << LINK_BITS_PER_SYMBOL << ",\"tat_ns\":" << LINK_TAT_NS << "}\n";
    vcd = sc_create_vcd_trace_file((directory + "/axi_wave").c_str());
    vcd->set_time_unit(1, SC_FS);
    sc_trace(vcd, clock, "ACLK"); sc_trace(vcd, resetn, "ARESETn");
    wires.trace(vcd);
    if (aou) aou->trace(vcd);
    SC_THREAD(reset);
    SC_METHOD(checkClock); sensitive << clock.posedge_event(); dont_initialize();
}
Bridge::~Bridge() = default;
void Bridge::reset() {
    resetn = false;
    wait(clock.period() * 3 + clock.period() / 2);
    while (aou && !aou->ready()) wait(clock.period());
    resetn = true;
}
gem5::Port& Bridge::gem5_getPort(const std::string& n, int) {
    if (n != "tlm") throw std::runtime_error("unknown AxiBridge port: " + n);
    return wrapper;
}
void Bridge::checkClock() { sc_assert(sc_time_stamp().value() == gem5::curTick()); }
void Bridge::finish() {
    if (finished) return;
    finished = true;
    AxiMasterStats stats{master.accepted, master.completed, master.maxActive,
                         master.capacityDenials, master.idle()};
    monitor.finish(clock.period().value(), &stats);
    if (aou) aou->finish(directory);
    if (vcd) {
        // gem5 can exit before the lowest-priority SystemC trace event runs.
        // Record current signal values at the SAME tick before closing. The
        // VCD destructor alone emits only a timestamp, losing the final edge.
        static_cast<sc_gem5::TraceFile*>(vcd)->trace(false);
        sc_close_vcd_trace_file(vcd);
        vcd = nullptr;
    }
}
}
