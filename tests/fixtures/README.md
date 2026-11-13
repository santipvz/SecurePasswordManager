# Vault compatibility fixtures

These encrypted files contain synthetic test data. They were generated with the Python implementation before the hexagonal architecture refactor. `password-v1.spm` uses a master password. `fido2-v2.spm` also contains a slot wrapped with a simulated FIDO2 PRF output.

The test inputs are recorded in [test_vault_compatibility.py](../test_vault_compatibility.py). Keep these fixtures fixed so a change to the reader and writer cannot silently break previously created vaults. Add a separate fixture when introducing a new format.
