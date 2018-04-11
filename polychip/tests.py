import sys
import unittest
from polychip import *
from gates import *


class PolychipTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dict = {
            'polygon_1hole_split_correctly': {
                'expected': {
                    'P2': {(Type.GATE, '1')},
                    'D1': {(Type.E1, '0'), (Type.E1, '1')},
                    'D2': {(Type.E0, '1'), (Type.E0, '0')},
                    'P1': {(Type.GATE, '0')}
                }
            },
            'metal_overlap_join': {
                'expected': {
                    'S1': {(Type.GATE, '0')},
                    'S2': {(Type.E0, '0')},
                    'S3': {(Type.E1, '0')}
                }
            },
            'poly_overlap_join': {
                'expected': {
                    'S1': {(Type.GATE, '0')},
                    'S2': {(Type.E0, '0')},
                    'S3': {(Type.E1, '0')}
                }
            },
            'diff_overlap_join': {
                'expected': {
                    'S1': {(Type.GATE, '0')},
                    'S2': {(Type.E0, '0')},
                    'S3': {(Type.E1, '0')}
                }
            },
            'partial_poly_overlap': {
                'expected': {
                }
            },
            'polychip_test_inverter': {
                'expected': {
                    'VCC': {(Type.E0, '0')},
                    'OUT': {(Type.GATE, '0'), (Type.E1, '0'), (Type.E0, '1')},
                    'GND': {(Type.E1, '1')}, 
                    'IN': {(Type.GATE, '1')}
                }
            },
            'rotated_labels': {
                'expected': {
                    'VCC': {(Type.E0, '0')},
                    'OUT': {(Type.GATE, '0'), (Type.E1, '0'), (Type.E0, '1')},
                    'GND': {(Type.E1, '1')}, 
                    'IN': {(Type.GATE, '1')}
                }
            },
            'power_transistor': {
                'expected': {
                    'PINX': {(Type.E1, '9'), (Type.E0, '7'), (Type.E0, '10'), (Type.E1, '15'), (Type.E1, '0'), 
                        (Type.E0, '12'), (Type.E0, '8'), (Type.E1, '11'), (Type.E0, '3'), (Type.E0, '1'), 
                        (Type.E0, '5'), (Type.E0, '14'), (Type.E0, '2'), (Type.E0, '6'), (Type.E0, '4'), (Type.E1, '13')},
                    'GND': {(Type.E0, '13'), (Type.E1, '10'), (Type.E0, '11'), (Type.E0, '9'), (Type.E1, '12'), 
                        (Type.E0, '0'), (Type.E0, '15'), (Type.E1, '14')},
                    'VCC': {(Type.E1, '3'), (Type.E1, '6'), (Type.E1, '4'), (Type.E1, '2'), (Type.E1, '5'), 
                        (Type.E1, '7'), (Type.E1, '1'), (Type.E1, '8')},
                    'X-': {(Type.GATE, '10'), (Type.GATE, '9'), (Type.GATE, '11'), (Type.GATE, '14'), 
                        (Type.GATE, '15'), (Type.GATE, '0'), (Type.GATE, '13'), (Type.GATE, '12')},
                    'X+': {(Type.GATE, '7'), (Type.GATE, '4'), (Type.GATE, '6'), (Type.GATE, '5'), (Type.GATE, '3'),
                        (Type.GATE, '2'), (Type.GATE, '8'), (Type.GATE, '1')}
                }
            },
            'power_transistors': {
                'expected': {
                    'PINX': {(Type.E0, '11'), (Type.E0, '14'), (Type.E0, '23'), (Type.E1, '22'), 
                        (Type.E0, '12'), (Type.E0, '19'), (Type.E1, '24'), (Type.E0, '9'), (Type.E1, '20'), 
                        (Type.E0, '15'), (Type.E1, '17'), (Type.E1, '25'), (Type.E0, '13'), (Type.E0, '10'), 
                        (Type.E0, '21'), (Type.E0, '16')}, 'PINY': {(Type.E0, '29'), (Type.E1, '32'), 
                        (Type.E0, '3'), (Type.E1, '30'), (Type.E0, '8'), (Type.E0, '0'), (Type.E0, '2'), 
                        (Type.E0, '1'), (Type.E1, '26'), (Type.E0, '27'), (Type.E0, '5'), (Type.E0, '31'), 
                        (Type.E0, '6'), (Type.E1, '28'), (Type.E0, '4'), (Type.E0, '7')},
                    'GND': {(Type.E1, '21'), (Type.E0, '30'), (Type.E0, '22'), (Type.E1, '29'), 
                        (Type.E0, '32'), (Type.E1, '19'), (Type.E1, '23'), (Type.E0, '17'), (Type.E0, '20'), 
                        (Type.E1, '0'), (Type.E0, '18'), (Type.E0, '26'), (Type.E1, '27'), (Type.E1, '31'), 
                        (Type.E0, '24'), (Type.E0, '28'), (Type.E0, '25')},
                    'VCC': {(Type.E1, '14'), (Type.E1, '15'), (Type.E1, '3'), (Type.E1, '5'), (Type.E1, '8'), 
                        (Type.E1, '16'), (Type.E1, '11'), (Type.E1, '1'), (Type.E1, '9'), (Type.E1, '2'), 
                        (Type.E1, '12'), (Type.E1, '6'), (Type.E1, '13'), (Type.E1, '7'), (Type.E1, '10'),
                        (Type.E1, '4')},
                    '__net__0': {(Type.E1, '18')}, 
                    'Y-': {(Type.GATE, '0'), (Type.GATE, '27'), (Type.GATE, '30'), (Type.GATE, '26'), 
                        (Type.GATE, '31'), (Type.GATE, '32'), (Type.GATE, '29'), (Type.GATE, '28')},
                    'X-': {(Type.GATE, '19'), (Type.GATE, '21'), (Type.GATE, '20'), (Type.GATE, '22'), 
                        (Type.GATE, '23'), (Type.GATE, '24'), (Type.GATE, '17'), (Type.GATE, '25')}, 
                    '__net__1': {(Type.GATE, '18')},
                    'Y+': {(Type.GATE, '7'), (Type.GATE, '5'), (Type.GATE, '2'), (Type.GATE, '6'), 
                        (Type.GATE, '1'), (Type.GATE, '4'), (Type.GATE, '3'), (Type.GATE, '8')},
                    'X+': {(Type.GATE, '9'), (Type.GATE, '10'), (Type.GATE, '16'), (Type.GATE, '15'), 
                        (Type.GATE, '12'), (Type.GATE, '11'), (Type.GATE, '14'), (Type.GATE, '13')}                
                }
            },
            'qnames': {
                'expected': {
                    'VCC': {(Type.E0, 'Q1')},
                    'OUT': {(Type.GATE, 'Q1'), (Type.E0, 'QA10.34'), (Type.E1, 'Q1')},
                    'GND': {(Type.E1, 'QA10.34')},
                    'IN': {(Type.GATE, 'QA10.34')}
                }
            },
            'sample1': {
                'expected': {
                    'X1': {(Type.GATE, '4')}, 
                    'L2': {(Type.GATE, '3')}, 
                    'X2': {(Type.E1, '4')}, 
                    'L4': {(Type.E1, '2'), (Type.E0, '1')}, 
                    'L1': {(Type.E0, '0'), (Type.E1, '5')}, 
                    'X3': {(Type.GATE, '0'), (Type.GATE, '2'), (Type.E1, '0'), (Type.E1, '1')}, 
                    '__net__0': {(Type.E0, '3'), (Type.E0, '4'), (Type.GATE, '1')}, 
                    '__net__1': {(Type.E0, '5'), (Type.E1, '3'), (Type.GATE, '5'), (Type.E0, '2')}                
                }
            },
            'compute_distance_properly': {
                'expected': {}
            },
            'endpoint_not_startpoint': {
                'expected': {}
            },
            'multipoly_path': {
                'expected': {}
            },
        }

    def assertListsEqualInAnyOrder(self, expected, actual):
        for e in expected:
            self.assertIn(e, actual, "Expected element {:s} is not in actual list {:s}".format(
                str(e), str(actual)))
        for a in actual:
            self.assertIn(a, expected, "Actual element {:s} is not in expected list {:s}".format(
                str(a), str(expected)))

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def do_test(self, testname):
        key = testname[5:]
        filename = "test/" + key + ".svg"
        netlist, _, _ = file_to_netlist(filename)
        self.assertEqual(self.test_dict[key]['expected'], netlist)
        # self.assertListsEqualInAnyOrder(self.test_dict[key]['expected'], netlist)

    def test_polygon_1hole_split_correctly(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_metal_overlap_join(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_poly_overlap_join(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_diff_overlap_join(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_polychip_test_inverter(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_rotated_labels(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_partial_poly_overlap(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_power_transistor(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_power_transistors(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_qnames(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_sample1(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_compute_distance_properly(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_endpoint_not_startpoint(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_multipoly_path(self):
        self.do_test(sys._getframe().f_code.co_name)

    def test_self_crossing(self):
        testname = sys._getframe().f_code.co_name
        key = testname[5:]
        filename = "test/" + key + ".svg"
        self.assertRaises(AssertionError, file_to_netlist, filename)

    def test_find_parallel_qs(self):
        filename = "test/polychip_test_parallel_qs.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(only(gates.pass_qs).qs), 1)
        q = only(only(gates.pass_qs).qs)
        self.assertIs(type(q), ParallelTransistor)
        self.assertEqual(q.num_qs(), 4)

    def test_find_lut(self):
        filename = "test/polychip_test_lut.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.luts), 1)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 0)
        self.assertEqual(len(gates.nands), 0)
        lut = only(gates.luts)
        self.assertEqual(set(lut.inputs), {"IN1", "IN2", "IN3", "IN4"})
        self.assertEqual(lut.output(), "OUT")
        self.assertEqual(lut.num_qs(), 5)
        self.assertEqual(set(lut.neg_ens), {"IN1", "IN2"})
        self.assertEqual(set(lut.non_neg_ens), {"IN3", "IN4"})
        self.assertEqual({q.name for q in lut.nor_input_qs}, {"QE1", "QE2", "QI3"})
        self.assertEqual(lut.output_power_q.name, "QP")
        self.assertEqual(len(gates.qs), 0)

    def test_find_inverter(self):
        filename = "test/polychip_test_inverter.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 1)
        inv = only(gates.nors)
        self.assertEqual(set(inv.inputs), {"IN"})
        self.assertEqual(inv.output(), "OUT")
        self.assertEqual(inv.num_qs(), 2)
        self.assertEqual(len(gates.qs), 0)

    def test_find_2nor(self):
        filename = "test/polychip_test_2nor.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 1)
        nor = only(gates.nors)
        self.assertEqual(set(nor.inputs), {"IN1", "IN2"})
        self.assertEqual(nor.output(), "OUT")
        self.assertEqual(nor.num_qs(), 3)
        self.assertEqual(len(gates.qs), 0)

    def test_find_3nand(self):
        filename = "test/polychip_test_nand.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 0)
        self.assertEqual(len(gates.nands), 1)
        nand = only(gates.nands)
        self.assertEqual(set(nand.inputs), {"IN1", "IN2", "IN3"})
        self.assertEqual(nand.output(), "OUT")
        self.assertEqual(nand.num_qs(), 4)
        self.assertEqual(len(gates.qs), 0)

    def test_find_pass_q(self):
        filename = "test/polychip_test_pass_q.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 2)
        self.assertEqual(len(gates.nands), 0)
        pass_q = only(gates.pass_qs)
        self.assertEqual(pass_q.name, "QPP")
        self.assertEqual(len(gates.qs), 0)

    def test_find_2mux(self):
        filename = "test/polychip_test_2mux.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 1)
        self.assertEqual(len(gates.nors), 0)
        mux = only(gates.muxes)
        self.assertEqual(set(mux.selected_inputs), {"X0", "X1"})
        self.assertEqual(set(mux.selecting_inputs), {"S0", "S1"})
        self.assertEqual(set(mux.inputs), {"X0", "X1", "S0", "S1"})
        self.assertEqual(mux.output(), "Y")
        self.assertEqual(mux.num_qs(), 2)
        self.assertEqual(len(gates.qs), 0)

    def test_find_power_mux(self):
        filename = "test/polychip_test_power_mux.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 1)
        self.assertEqual(len(gates.nors), 0)
        mux = only(gates.muxes)
        self.assertIs(type(mux), PowerMultiplexer)
        self.assertEqual(set(mux.selected_inputs), {"VCC", "GND"})
        self.assertEqual(set(mux.selecting_inputs), {"S0", "S1"})
        self.assertEqual(set(mux.inputs), {"S0", "S1"})
        self.assertEqual(mux.output(), "Y")
        self.assertEqual(mux.num_qs(), 2)
        self.assertEqual(len(gates.qs), 0)

    def test_find_power_inverter(self):
        filename = "test/polychip_test_power_inverter.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 1)
        inv = only(gates.nors)
        self.assertIs(type(inv), PowerNorGate)
        self.assertEqual(set(inv.inputs), {"IN"})
        self.assertEqual(inv.output(), "OUT")
        self.assertEqual(inv.num_qs(), 4)
        self.assertEqual(len(gates.qs), 0)

    def test_find_power_2nor(self):
        filename = "test/polychip_test_power_2nor.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 1)
        nor = only(gates.nors)
        self.assertIs(type(nor), PowerNorGate)
        self.assertEqual(set(nor.inputs), {"IN1", "IN2"})
        self.assertEqual(nor.output(), "OUT")
        self.assertEqual(nor.num_qs(), 6)
        self.assertEqual(len(gates.qs), 0)

    def test_find_tristate_inverter(self):
        filename = "test/polychip_test_tristate_inverter.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 0)
        self.assertEqual(len(gates.tristate_inverters), 1)
        zinv = only(gates.tristate_inverters)
        self.assertEqual(zinv.input(), "IN")
        self.assertEqual(zinv.output(), "OUT")
        self.assertEqual(zinv.noe, "/OE")
        self.assertEqual(zinv.num_qs(), 10)
        self.assertEqual(len(gates.qs), 0)

    def test_find_tristate_buffer(self):
        filename = "test/polychip_test_tristate_buffer.svg"
        netlist, qs, _ = file_to_netlist(filename)
        gates = Gates(netlist, qs)
        gates.find_all_the_things()

        self.assertEqual(len(gates.pass_qs), 1)
        self.assertEqual(len(gates.luts), 0)
        self.assertEqual(len(gates.muxes), 0)
        self.assertEqual(len(gates.nors), 0)
        self.assertEqual(len(gates.tristate_buffers), 1)
        zbuff = only(gates.tristate_buffers)
        self.assertEqual(zbuff.input(), "IN")
        self.assertEqual(zbuff.output(), "OUT")
        self.assertEqual(zbuff.noe, "/OE")
        self.assertEqual(zbuff.num_qs(), 10)
        self.assertEqual(len(gates.qs), 0)


if __name__ == '__main__':
    unittest.main()
