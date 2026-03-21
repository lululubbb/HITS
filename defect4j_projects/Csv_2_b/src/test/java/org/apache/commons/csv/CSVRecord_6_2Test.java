package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_6_2Test {

    private CSVRecord csvRecord;
    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    public void setUp() throws Exception {
        values = new String[] {"value1", "value2"};
        mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        // Use reflection to invoke package-private constructor
        csvRecord = createCSVRecord(values, mapping, null, 1L);
    }

    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber) throws Exception {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance((Object) values, (Object) mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    public void testIsSet_MappedAndIndexInRange() {
        assertTrue(csvRecord.isSet("col1"));
        assertTrue(csvRecord.isSet("col2"));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_MappedButIndexOutOfRange() throws Exception {
        mapping.put("col3", 2);
        CSVRecord record = createCSVRecord(values, mapping, null, 1L);
        assertFalse(record.isSet("col3"));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_NotMapped() {
        assertFalse(csvRecord.isSet("nonexistent"));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_NullName() {
        assertFalse(csvRecord.isSet(null));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_EmptyMapping() throws Exception {
        CSVRecord record = createCSVRecord(values, Collections.emptyMap(), null, 1L);
        assertFalse(record.isSet("col1"));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_EmptyValues() throws Exception {
        Map<String, Integer> map = new HashMap<>();
        map.put("col1", 0);
        CSVRecord record = createCSVRecord(new String[0], map, null, 1L);
        assertFalse(record.isSet("col1"));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_EmptyValuesAndEmptyMapping() throws Exception {
        CSVRecord record = createCSVRecord(new String[0], Collections.emptyMap(), null, 1L);
        assertFalse(record.isSet("col1"));
    }

    @Test
    @Timeout(8000)
    public void testIsSet_PrivateMethodInvocation() throws Exception {
        Method isMappedMethod = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        isMappedMethod.setAccessible(true);

        assertTrue((Boolean) isMappedMethod.invoke(csvRecord, "col1"));
        assertFalse((Boolean) isMappedMethod.invoke(csvRecord, "nonexistent"));
        assertFalse((Boolean) isMappedMethod.invoke(csvRecord, (Object) null));
    }
}