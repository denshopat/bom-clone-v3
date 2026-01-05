CREATE TABLE IF NOT EXISTS public.station_equipment_event (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bom_station_number integer NOT NULL,
    element text NOT NULL,
    action character varying(10),
    instrument_detail text,
    system text,
    event_date date,
    source_pdf text
);

CREATE TABLE IF NOT EXISTS public.station_equipment_element (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bom_station_number integer NOT NULL,
    element text NOT NULL,
    has_events character varying(1),
    source_pdf text
);

CREATE TABLE IF NOT EXISTS public.station_equipment_event_stage (
    bom_station_number text,
    element text,
    action text,
    instrument_detail text,
    system text,
    event_date text,
    source_pdf text
);
