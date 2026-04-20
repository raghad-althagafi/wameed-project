import unittest
from unittest.mock import patch
from Singleton.firebase_connection import FirebaseConnection


class TestFirebaseConnection(unittest.TestCase):

    def setUp(self):
        FirebaseConnection._db = None

    @patch("Singleton.firebase_connection.firebase_admin.initialize_app")
    @patch("Singleton.firebase_connection.credentials.Certificate")
    @patch("Singleton.firebase_connection.firebase_admin._apps", new=[])

    # Test that Firebase initializes correctly when not already initialized
    def test_initialize_runs_once(self, mock_cred, mock_init):
        FirebaseConnection.initialize()

        mock_cred.assert_called_once()
        mock_init.assert_called_once()

    @patch("Singleton.firebase_connection.firestore.client")
    @patch("Singleton.firebase_connection.firebase_admin.initialize_app")
    @patch("Singleton.firebase_connection.credentials.Certificate")
    @patch("Singleton.firebase_connection.firebase_admin._apps", new=[])

    # Test that get_db returns a database instance
    def test_get_db_returns_instance(self, mock_cred, mock_init, mock_client):
        mock_client.return_value = "mock_db"

        db = FirebaseConnection.get_db()

        self.assertEqual(db, "mock_db")
        mock_client.assert_called_once()

    @patch("Singleton.firebase_connection.firestore.client")
    @patch("Singleton.firebase_connection.credentials.Certificate")
    @patch("Singleton.firebase_connection.firebase_admin.initialize_app")
    @patch("Singleton.firebase_connection.firebase_admin._apps", new=[])
    
    # Test that database connection is reused (not created twice)
    def test_get_db_cached(self, mock_init, mock_cred, mock_client):
        mock_client.return_value = "mock_db"

        db1 = FirebaseConnection.get_db()
        db2 = FirebaseConnection.get_db()

        self.assertEqual(db1, db2)
        mock_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()