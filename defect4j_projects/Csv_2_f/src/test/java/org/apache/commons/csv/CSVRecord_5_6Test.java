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

class CSVRecord_5_6Test {

    private CSVRecord csvRecordWithMapping;
    private CSVRecord csvRecordWithoutMapping;
    private Map<String, Integer> mapping;

    @BeforeEach
    void setUp() throws Exception {
        mapping = new HashMap<>();
        mapping.put("header1", 0);
        mapping.put("header2", 1);

        String[] values = new String[] { "value1", "value2" };

        // Use reflection to access the package-private constructor
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        csvRecordWithMapping = constructor.newInstance((Object) values, mapping, null, 1L);
        csvRecordWithoutMapping = constructor.newInstance((Object) values, null, null, 1L);
    }

    @Test
    @Timeout(8000)
    void testIsMapped_NameInMapping_ReturnsTrue() {
        assertTrue(csvRecordWithMapping.isMapped("header1"));
        assertTrue(csvRecordWithMapping.isMapped("header2"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_NameNotInMapping_ReturnsFalse() {
        assertFalse(csvRecordWithMapping.isMapped("header3"));
        assertFalse(csvRecordWithMapping.isMapped(null));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_MappingIsNull_ReturnsFalse() {
        assertFalse(csvRecordWithoutMapping.isMapped("header1"));
        assertFalse(csvRecordWithoutMapping.isMapped(null));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_ReflectionInvocation() throws Exception {
        Method isMappedMethod = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        isMappedMethod.setAccessible(true);

        // Invoke with mapping present and key present
        Boolean result1 = (Boolean) isMappedMethod.invoke(csvRecordWithMapping, "header1");
        assertTrue(result1);

        // Invoke with mapping present and key absent
        Boolean result2 = (Boolean) isMappedMethod.invoke(csvRecordWithMapping, "unknown");
        assertFalse(result2);

        // Invoke with mapping null
        Boolean result3 = (Boolean) isMappedMethod.invoke(csvRecordWithoutMapping, "header1");
        assertFalse(result3);
    }
}