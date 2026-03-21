package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CSVRecord_4_4Test {

    @Test
    @Timeout(8000)
    void testIsConsistent_MappingIsNull() throws Exception {
        CSVRecord record = createCSVRecord(new String[]{"a", "b"}, null, "comment", 1L);
        assertTrue(record.isConsistent());
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_MappingSizeEqualsValuesLength() throws Exception {
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        CSVRecord record = createCSVRecord(new String[]{"a", "b"}, mapping, "comment", 1L);
        assertTrue(record.isConsistent());
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_MappingSizeNotEqualsValuesLength() throws Exception {
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        CSVRecord record = createCSVRecord(new String[]{"a", "b"}, mapping, "comment", 1L);
        assertFalse(record.isConsistent());
    }

    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber)
            throws NoSuchMethodException, IllegalAccessException, InvocationTargetException, InstantiationException {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance((Object) values, mapping, comment, recordNumber);
    }
}