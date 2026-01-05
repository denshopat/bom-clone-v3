--
-- PostgreSQL database dump
--

\restrict 6ZlY7mwCTomFioUWCezv7HOorMA4fYVqiDCckZdbt07HKcsIZw32AqBaik9EaUq

-- Dumped from database version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: product_code_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.product_code_enum AS ENUM (
    'IDCJAC0009',
    'IDCJAC0010',
    'IDCJAC0011'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: station; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.station (
    id integer NOT NULL,
    bom_station_number integer NOT NULL,
    dist integer,
    station_name character varying(100) NOT NULL,
    start_year integer,
    end_year integer,
    latitude double precision,
    longitude double precision,
    source character varying(30),
    state character varying(3) NOT NULL,
    height double precision,
    bar_height double precision,
    wmo integer,
    metadata_compiled date,
    bom_district_name text,
    identification character varying(30),
    network_classification character varying(100),
    station_purpose character varying(100),
    aws character varying(30),
    status character varying(20),
    note character varying(50)
);


--
-- Name: acornsat; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.acornsat AS
 SELECT station.id,
    station.bom_station_number,
    station.dist,
    station.station_name,
    station.start_year,
    station.end_year,
    station.latitude,
    station.longitude,
    station.source,
    station.state,
    station.height,
    station.bar_height,
    station.wmo,
    station.metadata_compiled,
    station.bom_district_name,
    station.identification,
    station.network_classification,
    station.station_purpose,
    station.aws,
    station.status,
    station.note
   FROM public.station
  WHERE (station.bom_station_number = ANY (ARRAY[23090, 9741, 15590, 40004, 36007, 63005, 38026, 38003, 48245, 9510, 40842, 3003, 39128, 29077, 96003, 72161, 31011, 37010, 70351, 22823, 94010, 9518, 40043, 90015, 6011, 18012, 44021, 34084, 48027, 59040, 10286, 8039, 14015, 74258, 65070, 9789, 11003, 11052, 84016, 39066, 30124, 8051, 13017, 94220, 55024, 2012, 94029, 27058, 56242, 12038, 1019, 10579, 80023, 18044, 92045, 91311, 87031, 5007, 36031, 91293, 33119, 4106, 17031, 7045, 86071, 10092, 76031, 42112, 8296, 53115, 69018, 26021, 78015, 29063, 68072, 23373, 17043, 84145, 28004, 9021, 68151, 4032, 18192, 60139, 15666, 67105, 30045, 26026, 39083, 82039, 85072, 61363, 21133, 43109, 66062, 16098, 15135, 45025, 46037, 32040, 14825, 72150, 52088, 10917, 27045, 46043, 61078, 85096, 5026, 16001, 73054, 58012]));


--
-- Name: daily_max_temperature; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_max_temperature (
    id integer NOT NULL,
    bom_station_number integer NOT NULL,
    date date NOT NULL,
    max_temperature numeric(4,1),
    accumulation_days integer,
    quality boolean,
    product_code public.product_code_enum NOT NULL
);


--
-- Name: daily_max_temperature_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.daily_max_temperature ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.daily_max_temperature_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: daily_min_temperature; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_min_temperature (
    id integer NOT NULL,
    bom_station_number integer NOT NULL,
    date date NOT NULL,
    min_temperature numeric(4,1),
    accumulation_days integer,
    quality boolean,
    product_code public.product_code_enum NOT NULL
);


--
-- Name: daily_min_temperature_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.daily_min_temperature ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.daily_min_temperature_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: daily_rainfall; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_rainfall (
    id integer NOT NULL,
    bom_station_number integer NOT NULL,
    date date NOT NULL,
    rainfall_amount numeric(6,2),
    rainfall_period integer,
    quality boolean,
    product_code public.product_code_enum NOT NULL
);


--
-- Name: daily_rainfall_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.daily_rainfall ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.daily_rainfall_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: station_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.station_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: station_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.station_id_seq OWNED BY public.station.id;


--
-- Name: station id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.station ALTER COLUMN id SET DEFAULT nextval('public.station_id_seq'::regclass);


--
-- Name: daily_max_temperature daily_max_temperature_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_max_temperature
    ADD CONSTRAINT daily_max_temperature_pkey PRIMARY KEY (id);


--
-- Name: daily_min_temperature daily_min_temperature_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_min_temperature
    ADD CONSTRAINT daily_min_temperature_pkey PRIMARY KEY (id);


--
-- Name: daily_rainfall daily_rainfall_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_rainfall
    ADD CONSTRAINT daily_rainfall_pkey PRIMARY KEY (id);


--
-- Name: station station_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.station
    ADD CONSTRAINT station_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict 6ZlY7mwCTomFioUWCezv7HOorMA4fYVqiDCckZdbt07HKcsIZw32AqBaik9EaUq

