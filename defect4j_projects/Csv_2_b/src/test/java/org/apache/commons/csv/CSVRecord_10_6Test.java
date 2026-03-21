package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_10_6Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    void setUp() throws Exception {
        values = new String[] {"value1", "value2"};
        mapping = Collections.singletonMap("header1", 0);
        comment = "a comment";
        recordNumber = 42L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        if (!Modifier.isPublic(constructor.getModifiers()) || !Modifier.isPublic(CSVRecord.class.getModifiers())) {
            constructor.setAccessible(true);
        }
        csvRecord = constructor.newInstance(values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    void testGetRecordNumber() {
        long result = csvRecord.getRecordNumber();
        assertEquals(recordNumber, result);
    }
}