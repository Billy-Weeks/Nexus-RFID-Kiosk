# Nexus RFID Kiosk // Access Terminal

A hardware-integrated Python kiosk application designed for secure RFID/NFC event scanning. Features an automated initialization lifecycle, localized state management, and real-time cloud synchronization via Supabase.

https://github.com/user-attachments/assets/b95fa574-d1e3-47b6-b3eb-73bdc5b81451


## System Features


* **Standalone Deployment:** Fully compiled executable requiring no local Python environment or dependency management for the end-user.
* **Automated State Detection:** Dynamically detects unconfigured environments on boot and safely routes administrators to a secure initialization portal.
* **Cryptographic State Management:** Securely writes and manages required environment variables and database keys to local disk.
* **Process Replacement Architecture:** Utilizes low-level system commands to gracefully kill and resurrect the compiled kiosk environment after initialization, without requiring manual operating system reboots.
* **Hardware Integration:** Dedicated listening architecture optimized for continuous RFID/NFC payload scanning.
* **Real-Time Cloud Sync:** Instantaneous attendance and credential verification via Supabase integration.

---

## Quick Start & Setup

### Prerequisites
* A Supabase project with your generated API URL and Anon Key.
* An active RFID/NFC hardware scanner connected via USB.


### Installation

1. **Download the Release:**
   * Navigate to the **Releases** section on the right side of this GitHub repository.
   * Download the latest executable file (e.g., `NexusKiosk.exe`).

2. **Boot the Kiosk:**
   * Double-click the downloaded executable to launch the application. *(No terminal or dependency installations required).*

3. **Initialize the System:**
   * On first boot, the system will detect a missing `.env` file and seamlessly route you to the setup portal.
   * Enter your Club Name, Supabase credentials, and Admin keys.
   * The application will automatically save your secrets and reboot itself into the active kiosk state.

---

## Technical Deep Dive: Process Replacement

One of the core challenges of building a continuous-run kiosk compiled as a standalone executable is handling environment variable injection dynamically. 

This system solves stale memory states using a "Phoenix Protocol" approach. When the Initialization Portal completes its write operations to the `.env` file, the application clears all active web sessions, halts background threads, and executes an `os.execv` command. This completely replaces the currently running executable process with a brand-new instance of itself, forcing the system to read the freshly injected API keys from the disk while providing a seamless, cinematic loading screen to the user.


---


## Hardware Specifications

* **Scanner Interface:** Plug-and-play USB RFID/NFC Reader (Keyboard Emulation).
* **Target Environment:** Windows OS (Compiled via PyInstaller).

---


## Environment Variables & Local State


While the application utilizes Supabase for cloud synchronization, it relies on a local `.env` file for state management and API access. These keys are automatically generated and secured by the Initialization Portal on first boot:

* `CLUB_NAME`: The designated display name of the active organization.
* `SUPABASE_URL`: The API routing URL for the Supabase project.
* `SUPABASE_KEY`: The Anon/Public key required for database read/write access.
* `ADMIN_PASSWORD`: The secure credential required to access administrative functions.
* `ESCAPE_PASSWORD`: The specific string (must begin with a letter) used to safely terminate the kiosk environment.
* `SESSION_SECRET_KEY`: A 32-byte hex hash automatically generated per-session to encrypt local cookies and prevent cross-site request forgery.

---

## Database Schema

The kiosk utilizes Supabase (PostgreSQL) for real-time cloud synchronization. To run this application, your database must contain the following two tables:



### Table: `users`
Stores the member directory and RFID tag assignments.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `user_id` | `uuid` | Primary Key | Auto-generated unique identifier. |
| `cin` | `text` | Unique, Not Null | Campus Identification Number. |
| `first_name` | `text` | Not Null | Member's first name. |
| `last_name` | `text` | Not Null | Member's last name. |
| `email` | `text` | Not Null | Contact email address. |
| `major` | `text` | Not Null | Declared field of study. |
| `card_id` | `text` | Unique, Nullable | The raw RFID/NFC payload assigned to the user. |
| `upload_tag` | `text` | Nullable | Batch processing tag for bulk CSV imports. |

### Table: `attendance_log`
Records timestamped check-in events.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `log_id` | `bigint` | Primary Key | Auto-incrementing log identifier. |
| `user_id` | `uuid` | Not Null | References the specific user who scanned in. |
| `scan_time` | `timestamptz` | Not Null | Auto-generated timestamp of the scan (defaults to `now()`). |
| `event_name` | `text` | Nullable | The active event occurring during the scan. |

<details>
<summary><b>Click here for Quick-Setup SQL</b></summary>
</details>

Execute the following snippet in your Supabase SQL Editor to instantly generate the required schema:

```
sql
create table public.users (
  user_id uuid not null default gen_random_uuid (),
  cin text not null,
  first_name text not null,
  last_name text not null,
  email text not null,
  major text not null,
  card_id text null,
  upload_tag text null,
  constraint users_pkey primary key (user_id),
  constraint users_card_id_key unique (card_id),
  constraint users_cin_key unique (cin),
  constraint users_user_id_key unique (user_id)
);

create table public.attendance_log (
  log_id bigint generated by default as identity not null,
  user_id uuid not null,
  scan_time timestamp with time zone not null default now(),
  event_name text null,
  constraint attendance_log_pkey primary key (log_id)
);
```
