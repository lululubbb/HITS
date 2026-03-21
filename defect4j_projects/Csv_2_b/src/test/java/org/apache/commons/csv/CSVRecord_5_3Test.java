package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_5_3Test {

    private Map<String, Integer> mappingWithKeys;
    private Map<String, Integer> emptyMapping;

    @BeforeEach
    void setUp() {
        mappingWithKeys = new HashMap<>();
        mappingWithKeys.put("key1", 0);
        mappingWithKeys.put("key2", 1);
        emptyMapping = Collections.emptyMap();
    }

    @Test
    @Timeout(8000)
    void testIsMapped_mappingIsNull() throws Exception {
        // Create CSVRecord with null mapping using reflection to invoke constructor
        CSVRecord record = createCSVRecordWithMapping(null);
        // isMapped should return false when mapping is null
        assertFalse(record.isMapped("anyKey"));
        assertFalse(record.isMapped(null));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_mappingDoesNotContainKey() throws Exception {
        CSVRecord record = createCSVRecordWithMapping(emptyMapping);
        // mapping is empty, so any key returns false
        assertFalse(record.isMapped("missingKey"));
        assertFalse(record.isMapped(null));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_mappingContainsKey() throws Exception {
        CSVRecord record = createCSVRecordWithMapping(mappingWithKeys);
        // mapping contains "key1" and "key2"
        assertTrue(record.isMapped("key1"));
        assertTrue(record.isMapped("key2"));
        assertFalse(record.isMapped("key3"));
        assertFalse(record.isMapped(null));
    }

    // Helper method to create CSVRecord instance with given mapping using reflection
    private CSVRecord createCSVRecordWithMapping(Map<String, Integer> mapping) throws Exception {
        String[] values = new String[] { "value1", "value2" };
        String comment = null;
        long recordNumber = 1L;
        // CSVRecord constructor is package-private, use reflection to access it
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance((Object) values, mapping, comment, recordNumber);
    }

}