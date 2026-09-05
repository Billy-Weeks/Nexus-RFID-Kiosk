# Nexus RFID Kiosk // Access Terminal

A hardware-integrated Python kiosk application designed for secure RFID/NFC event scanning. Features an automated initialization lifecycle, localized state management, and real-time cloud synchronization via Supabase.

https://github.com/user-attachments/assets/b95fa574-d1e3-47b6-b3eb-73bdc5b81451

## Features

### Admin & User Features
* **Batch User Additions:** Reads from a .csv file (such as from a Google Doc or Excel spreadsheet), adds and assigns RFID cards to a large batch of users at once. Useful for beginning of year/semester events.
* **Add Onsite:** Gives clubs/event coordinators the ability to add members during the event. Updates database in realtime.
* **Self-Identifying Enrollment:** The onsite flow no longer assumes every scanned card belongs to a stranger. A member taps their card and supplies only the three details they already know by heart — first name, last name, and email — which the system uses as an identity *confirmation* rather than raw data entry. Recognized members (including those pre-loaded via CSV) have the card silently bound to their existing record, while unknown members are progressively disclosed a second form requesting CIN and Major. Redundant data entry is eliminated for anyone already in the directory.
* **Enrollment as Check-In:** Registration and attendance are collapsed into a single pass. Any member who completes the onsite flow during a live event is automatically written to the attendance log, removing the need to enroll a member and then immediately re-scan them at the terminal. When no event is active, enrollment still completes and the interface explicitly reports that attendance was *not* recorded, ensuring the operator is never misled about a member's presence.
* **Identity Collision Guarding:** Defensive checks prevent silent data corruption during self-enrollment. An email that resolves to a record under a different name is refused outright rather than being bound to the wrong person, a member who already owns a registered card is checked in without overwriting their existing credential, and a CIN conflict escalates to a club officer instead of failing to a raw server error.
* **Active Session Recovery** The dashboard intelligently tracks active event states via secure session cookies. If an admin navigates away from the scanning terminal during a live event, a "Return to Event" gateway ensures they can seamlessly resume the session without losing context or requiring reentry of event details.
* **Centralized Admin Hub** Complex operations (User Management, NFC Provisioning, Lost & Found) are cleanly decoupled from the main dashboard into a dedicated Admin Tools hub, streamlining the primary interface and preventing desctructive accidental clicks.
* **Dynamic Event Naming:** Each event can have different names (i.e. Workshop #2, Mock Technical Interview Event, etc.). Allows for separating attendance by event.
* **Start & Stop Event:** Once an event begins, each member scanned in is attached to that event. At the end of the event, the admin or coordinator can stop the event, setting up for future events.
* **Lost & Found:** Function allows for club officers to scan a lost card and retrieve the name of the owner by visual feedback on the screen.
* **Member Confirmation:** When member scans/taps into event, their name splashes on the screen giving visual confirmation of correct member. 
* **Logout:** Admin has the ability to logout of the system, giving the ability to lock terminal for security reasons. 
* **System Shutdown:** Performs a complete shutdown of the program, ensuring data has been saved to the database, and admin has been signed out complely. 
* **Admin NFC Escape Sequence:** Allows administrators to use a designated NFC tag to exit scan loops, replacing the need for manual keyboard escape sequences
* **Secure Admin Provisioning** Dedicated `/admin_tools` workflow for registering new system administrators with First Name, Last Name, Club Role, and a uniquely assigned NFC credential.
* **Live Attendance Dashboard** A real-time, terminal-styled interface that asynchronously tracks event check-ins. It automatically fetches and updates the screen with new scans every few seconds without ever requiring a manual page refresh.
* **Historical Event Archive** A dedicated analytics portal allowing administrators to query and review attendance records for any past event. It features a defensive-programmed UI that dynamically populates dropdown menus based on real database records.
* **Card Flexibility** Kiosk now supports a wide variety of RFID/NFC card types, including School ID cards, allowing for clubs to be cost effective and use already issued School ID's as club check-in tool. Student identity is still protected as ONLY the card id is recorded and used to confirm membership.
* **Attendance Counts** Analytics portal now includes a live count of total attendance for each event and historical events.



### System Architecture


* **Standalone Deployment:** Fully compiled executable requiring no local Python environment or dependency management for the end-user.
* **Automated State Detection:** Dynamically detects unconfigured environments on boot and safely routes administrators to a secure initialization portal.
* **Cryptographic State Management:** Securely writes and manages required environment variables and database keys to local disk.
* **Process Replacement Architecture:** Utilizes low-level system commands to gracefully kill and resurrect the compiled kiosk environment after initialization, without requiring manual operating system reboots.
* **Hardware Integration:** Dedicated listening architecture optimized for continuous RFID/NFC payload scanning.
* **Real-Time Cloud Sync:** Instantaneous attendance and credential verification via Supabase integration.
* **Customer Hardware-Level Form Validation** Bypasses standard, immersion-breaking browser alerts (via HTML5 `novalidate`) in favor of a customer JavaScript validation loop. Unfilled inputs are dynamically caught using `.checkValidity()` and `.requestSubmit()`, instantly triggering localized, red glowing CSS error stateson specific missing fields without reloading the page or losing terminal state.
* **Deadlock Prevention** Physical scanner inputs are automatically wiped via JavaScripty upon both successful and failed form submission, preventing the scanner hardware from "locking up" if an admin forgets a required field.
* **Custom REST API Endpoints:** Decouples the frontend UI from backend database queries using dedicated JSON-serving API routes (e.g., `/api/live-attendance`), allowing asynchronous JavaScript polling to handle real-time data cleanly and efficiently.
* **Component-Driven UI Design:** Utilizes modular, flexbox-based CSS architecture to maintain a consistent, physical-hardware aesthetic across both live and historical data views, prioritizing code reuse.


---

## Quick Start & Setup

### Prerequisites
* A Supabase project with your generated API URL and Anon Key. _(Important: You must configure your database tables BEFORE launching the application. See the **Database Schema** section below for the required SQL script)._ 
* An active RFID/NFC hardware scanner connected via USB.


### Installation

1. **Download the Release:**
   * Navigate to the **Releases** section on the right side of this GitHub repository.
   * Download the latest executable file (`NexusKiosk-Win.exe`).

2. **Boot the Kiosk:**
   * Double-click the downloaded executable to launch the application. *(No terminal or dependency installations required).*

3. **Initialize the System:**
   * On first boot, the system will detect a missing `.env` file and seamlessly route you to the setup portal.
   * Enter your Club Name, Supabase credentials, and Admin keys.
   * The application will automatically save your secrets and reboot itself into the active kiosk state.

---


## Hardware Specifications

* **Scanner Interface:** Plug-and-play USB RFID/NFC Reader (Keyboard Emulation).
* **Target Environment:** Windows OS (Compiled via PyInstaller).

---


## Environment Variables & Local State


While the application utilizes Supabase for cloud synchronization, it relies on a local `.env` file for state management and API access. These keys are securely written to the local disk via the _Initialization Portal_ on first boot, with the exception of the session key which is auto-generated:

* `CLUB_NAME`: The designated display name of the active organization.
* `SUPABASE_URL`: The API routing URL for the Supabase project.
* `SUPABASE_KEY`: The Anon/Public key required for database read/write access.
* `ADMIN_PASSWORD`: The secure credential required to access administrative functions.
* `ESCAPE_PASSWORD`: The specific string (must begin with a letter) used to safely terminate the kiosk environment.
* `SESSION_SECRET_KEY`: A 32-byte hex hash automatically generated per-session to encrypt local cookies and prevent cross-site request forgery.

---

## Database Schema

The kiosk utilizes Supabase (PostgreSQL) for real-time cloud synchronization. To run this application, your database must contain the following three tables:



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
| `user_id` | `uuid` | Not Null, Foreign Key → `users.user_id` | References the specific user who scanned in. The foreign key is **required** &mdash; the analytics and archive views join attendance back to the member directory, and PostgREST rejects that join if the relationship is not declared. |
| `scan_time` | `timestamptz` | Not Null | Auto-generated timestamp of the scan (defaults to `now()`). |
| `event_name` | `text` | Nullable | The active event occurring during the scan. |

### Table: `admin`
Stores system administrators and their privileged physical credentials

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `nat_id` | `uuid` | Primary Key | Auto-generated unique identifier for the administrator. |
| `nfc_id` | `text` | Unique, Not Null | The unique physical hardware identifier of the assigned NFC tag. |
| `first` | `text` | Not Null | Adminstrator's first name. |
| `last` | `text` | Not Null | Adminstrator's last name. |
| `role` | `text` | Not Null | The official title or position held within the club. |


<details>
<summary><b>Click here for Quick-Setup SQL</b></summary>

Execute the following snippet in your Supabase SQL Editor to instantly generate the required schema:

```sql
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
  constraint attendance_log_pkey primary key (log_id),
  -- Required: the analytics and archive views join attendance back to users.
  -- Without this foreign key the join is rejected outright (PostgREST PGRST200).
  constraint attendance_log_user_id_fkey foreign key (user_id)
    references public.users (user_id) on delete cascade
);

create table public.admin (
  nat_id uuid not null default gen_random_uuid (),
  nfc_id text not null,
  first text not null default ''::text,
  last text not null default ''::text,
  role text not null default ''::text,
  constraint admin_pkey primary key (nat_id),
  constraint admin_nfc_id_key unique (nfc_id)
);
```

</details>

<details>
<summary><b>Upgrading an existing database (missing attendance relationship)</b></summary>

Databases created before the foreign key was documented will load the dashboard normally
but fail on the analytics and archive views with
`PGRST200: Could not find a relationship between 'attendance_log' and 'users'`.

Check for attendance rows whose member no longer exists &mdash; the constraint cannot be
added while any remain:

```sql
select a.* from public.attendance_log a
left join public.users u on u.user_id = a.user_id
where u.user_id is null;
```

If that returns rows, remove them (the member record is gone, so the entries cannot be
attributed):

```sql
delete from public.attendance_log a
where not exists (select 1 from public.users u where u.user_id = a.user_id);
```

Then declare the relationship:

```sql
alter table public.attendance_log
  add constraint attendance_log_user_id_fkey
  foreign key (user_id) references public.users (user_id)
  on delete cascade;
```

Supabase refreshes its schema cache within a few seconds. To force it immediately, run
`notify pgrst, 'reload schema';`

</details>

---


## Technical Deep Dive: Process Replacement

One of the core challenges of building a continuous-run kiosk compiled as a standalone executable is handling environment variable injection dynamically. 

This system solves stale memory states using a "Phoenix Protocol" approach. When the Initialization Portal completes its write operations to the `.env` file, the application clears all active web sessions, halts background threads, and executes an `os.execv` command. This completely replaces the currently running executable process with a brand-new instance of itself, forcing the system to read the freshly injected API keys from the disk while providing a seamless, cinematic loading screen to the user.


---


## Future Improvements

* **Cross-Platform Compilation:** Future releases will also have executables available for download for macOS and Linux operating systems.
* **Dynamic Schema Generation:** Implement dynamic table creation within the Python architecture to automatically generate required database tables on initial setup.
