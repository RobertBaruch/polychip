import sys
import unittest
from polychip import *

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
        netlist, qdata = file_to_netlist(filename)
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

if __name__ == '__main__':
    unittest.main()
