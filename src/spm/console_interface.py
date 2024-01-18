"""Console interface to manage passwords."""
import argparse
from .sec_pass_manager import PasswordManager

def main():
    """Main function to manage passwords from the console."""
    parser = argparse.ArgumentParser(description='Manage your passwords from the console.')

    parser.add_argument('action', choices=['create', 'edit', 'delete'],
                        help='Action to perform.')
    parser.add_argument('--filename', '-f', required=True,
                        help='The file you want to create, edit, or delete.')
    parser.add_argument('--username', '-u',
                        help='The username you want to use.')
    parser.add_argument('--length', '-l', type=str, default='10',
                        help='The length of the password you want to generate.')

    args = parser.parse_args()

    password_manager = PasswordManager()

    if args.action == 'create':
        password_manager.create_password(args.filename, args.username, args.length)
    elif args.action == 'edit':
        password_manager.edit_password(args.filename, args.username, args.length)
    elif args.action == 'delete':
        password_manager.delete_password(args.filename)

if __name__ == '__main__':
    main()
