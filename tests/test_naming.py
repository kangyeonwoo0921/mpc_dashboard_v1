import unittest
from src.naming import column_name,rafter_name,vent_name,bed_name


class NamingTests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(column_name("main",1,1),"GH_COL_MAIN_X001_Y01")
        self.assertEqual(rafter_name(5,2),"GH_RAFTER_X005_S02")
        self.assertEqual(vent_name(4),"GH_VENT_S04_01")
        self.assertEqual(bed_name(3,4),"GH_BED_S03_R04")

    def test_unique_and_repeatable(self):
        a=[bed_name(s,r) for s in range(1,5) for r in range(1,6)]
        self.assertEqual(len(set(a)),20)
        self.assertEqual(a,[bed_name(s,r) for s in range(1,5) for r in range(1,6)])


if __name__=="__main__":
    unittest.main()
