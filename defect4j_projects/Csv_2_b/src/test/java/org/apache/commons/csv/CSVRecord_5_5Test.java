package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_5_5Test {

    private Map<String, Integer> mapping;
    private String[] values;
    private String comment;
    private long recordNumber;

    @BeforeEach
    void setUp() {
        values = new String[] {"value1", "value2"};
        comment = "comment";
        recordNumber = 1L;
    }

    @Test
    @Timeout(8000)
    void testIsMapped_MappingNull() {
        CSVRecord record = new CSVRecord(values, null, comment, recordNumber);
        assertFalse(record.isMapped("anyName"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_MappingNotContainsKey() {
        mapping = new HashMap<>();
        mapping.put("key1", 0);
        CSVRecord record = new CSVRecord(values, mapping, comment, recordNumber);
        assertFalse(record.isMapped("missingKey"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_MappingContainsKey() {
        mapping = new HashMap<>();
        mapping.put("key1", 0);
        CSVRecord record = new CSVRecord(values, mapping, comment, recordNumber);
        assertTrue(record.isMapped("key1"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_PrivateMethodInvocation() throws Exception {
        mapping = new HashMap<>();
        mapping.put("key1", 0);
        CSVRecord record = new CSVRecord(values, mapping, comment, recordNumber);

        Method method = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        method.setAccessible(true);

        // invoke with existing key
        boolean resultExists = (boolean) method.invoke(record, "key1");
        assertTrue(resultExists);

        // invoke with non-existing key
        boolean resultNotExists = (boolean) method.invoke(record, "notExist");
        assertFalse(resultNotExists);
    }
}