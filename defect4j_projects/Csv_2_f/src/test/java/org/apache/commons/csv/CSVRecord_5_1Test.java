package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_5_1Test {

    private CSVRecord csvRecordWithMapping;
    private CSVRecord csvRecordWithoutMapping;
    private Map<String, Integer> mapping;

    @BeforeEach
    void setUp() throws Exception {
        mapping = new HashMap<>();
        mapping.put("header1", 0);
        mapping.put("header2", 1);

        String[] values = new String[] {"value1", "value2"};

        // Use reflection to access the package-private constructor
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        csvRecordWithMapping = constructor.newInstance(values, mapping, "comment", 1L);
        csvRecordWithoutMapping = constructor.newInstance(values, null, "comment", 1L);
    }

    @Test
    @Timeout(8000)
    void testIsMapped_existingKey() {
        assertTrue(csvRecordWithMapping.isMapped("header1"));
        assertTrue(csvRecordWithMapping.isMapped("header2"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_nonExistingKey() {
        assertFalse(csvRecordWithMapping.isMapped("header3"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_nullMapping() {
        assertFalse(csvRecordWithoutMapping.isMapped("header1"));
        assertFalse(csvRecordWithoutMapping.isMapped(null));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_nullName() {
        // mapping contains keys, but name is null
        assertFalse(csvRecordWithMapping.isMapped(null));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_privateMethodInvocation() throws Exception {
        // Use reflection to invoke the isMapped method (even though it's public)
        Method method = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        method.setAccessible(true);

        Boolean result1 = (Boolean) method.invoke(csvRecordWithMapping, "header1");
        assertTrue(result1);

        Boolean result2 = (Boolean) method.invoke(csvRecordWithMapping, "nonexistent");
        assertFalse(result2);

        Boolean result3 = (Boolean) method.invoke(csvRecordWithoutMapping, "header1");
        assertFalse(result3);
    }
}