import argparse

from core_data_modules.logging import Logger
from storage.google_cloud import google_cloud_utils

from rapid_pro_tools.rapid_pro_client import RapidProClient

log = Logger(__name__)
log.set_project_name("CopyContacts")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copies contacts from one Rapid Pro instance to another")

    parser.add_argument("google_cloud_credentials_file_path", metavar="google-cloud-credentials-file-path",
                        help="Path to a Google Cloud service account credentials file to use to access the "
                             "credentials bucket")
    parser.add_argument("source_domain", metavar="source-domain",
                        help="Domain that the source instance of Rapid Pro is running on")
    parser.add_argument("source_credentials_url", metavar="source-credentials-url",
                        help="GS URL to the organisation access token file for authenticating to the source instance")
    parser.add_argument("target_domain", metavar="target-domain",
                        help="Domain that the target instance of Rapid Pro is running on")
    parser.add_argument("target_credentials_url", metavar="target-credentials-url",
                        help="GS URL to the organisation access token file for authenticating to the target instance")

    args = parser.parse_args()

    google_cloud_credentials_file_path = args.google_cloud_credentials_file_path
    source_domain = args.source_domain
    source_credentials_url = args.source_credentials_url
    target_domain = args.target_domain
    target_credentials_url = args.target_credentials_url

    # Initialise the source/target instances
    log.info("Downloading the source instance access token...")
    source_token = google_cloud_utils.download_blob_to_string(
        google_cloud_credentials_file_path, source_credentials_url).strip()
    source_instance = RapidProClient(source_domain, source_token)

    log.info("Downloading the target instance access token...")
    target_token = google_cloud_utils.download_blob_to_string(
        google_cloud_credentials_file_path, target_credentials_url).strip()
    target_instance = RapidProClient(target_domain, target_token)

    # For each contact field in the source instance, create a matching contact field in the target instance if it
    # does not already exist
    log.info("Copying contact fields...")
    source_fields = source_instance.get_fields()
    target_field_keys = {f.key for f in target_instance.get_fields()}
    for field in source_fields:
        if field.key not in target_field_keys:
            target_instance.create_field(field.label)
    log.info("Contact fields copied")

    log.info("Fetching all contacts from the source instance...")
    contacts = source_instance.get_raw_contacts()
    log.info(f"Fetched {len(contacts)} contacts")

    log.info("Updating contacts in the target instance...")
    # Update each contact's name and fields.
    # Language, groups, blocked, and stopped properties are not touched.
    multiple_urns_count = 0
    telephone_with_no_country_code_count = 0
    updated_count = 0
    for i, contact in enumerate(contacts):
        log.debug(f"Updating contact {i + 1}/{len(contacts)}...")
        if len(contact.urns) != 1:
            log.warning(f"Found a contact in the source instance with multiple URNS. "
                        f"The RapidPro UUID is '{contact.uuid}'")
            multiple_urns_count += 1
            continue
        if contact.urns[0].startswith("tel:") and not contact.urns[0].startswith("tel:+"):
            log.warning(f"Found a contact in the source instance with a telephone number that has no country "
                        f"code; skipping. The RapidPro UUID is '{contact.uuid}'")
            telephone_with_no_country_code_count += 1
            continue
        if contact.name == "":
            contact.name = None
        target_instance.update_contact(contact.urns[0], contact.name, contact.fields)
        updated_count += 1

    log.info(f"Done. Copied {updated_count} contacts. Failed to copy {multiple_urns_count} contacts with multiple "
             f"URNS, and {telephone_with_no_country_code_count} contacts with a telephone number but no country code")
