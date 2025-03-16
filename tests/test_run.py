import unittest
import os
import sys

def run_tests():
    """Run all tests."""
    # Find all test files
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = [f for f in os.listdir(test_dir) if f.startswith('test_') and f.endswith('.py')]
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add all tests to the suite
    for test_file in test_files:
        if test_file == 'test_run.py':
            continue
        
        module_name = test_file[:-3]  # Remove .py extension
        
        # Import the module
        module = __import__(module_name)
        
        # Add all test cases from the module
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                test_suite.addTest(unittest.makeSuite(obj))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Return success/failure
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
